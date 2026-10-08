;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: CDLA-Permissive-2.0
;;
;; The clj-urpx half of dev/cross_check_scenario_cost_models.py. Run by that script,
;; never on its own:
;;
;;   clojure -M dev/cross_check_scenario_cost_models.clj <instant> <combining-policy> \
;;           <namespace> <other-namespace>...
;;
;; It answers three questions: what do <namespace>/enumerate-pairs and
;; <namespace>/enumerate return over this corpus at that instant, what node does
;; <namespace>/node build for each model under <namespace>/rate-plans-iri, named
;; by <namespace>/rate-plans-name, and if they cannot be asked, WHY not.
;; <namespace> is urpx.scenario-cost-model, the clj-urpx 0.37.0 API plus its 0.43.0 `prepare`. The names after it are probed only to say which one
;; is present when <namespace> is not; this probe implements none of their APIs.
;; Every answer is a single XC- line on stdout, so the caller reads a state
;; rather than inferring one from an exit code that a JVM warning could muddy.
;;
;;   XC-STATE ns-absent <names>    neither <namespace> nor any other name is on
;;                                 the classpath
;;   XC-STATE ns-renamed <name>    <namespace> is absent and another name loads
;;   XC-STATE ns-load-error        <namespace> is on the classpath, and loading
;;                                 it threw
;;   XC-STATE ns-present-var-absent it loaded, and a var this probe calls is not
;;                                 there
;;   XC-STATE documents-error      the vars are there and the corpus would not load
;;   XC-STATE call-error           the vars are there and calling one threw
;;   XC-STATE shape-error          it returned something that is not a pair set
;;   XC-STATE pairs                followed by XC-PAIR lines and XC-END,
;;                                 then either XC-MODELS-ERROR <detail> or
;;                                 XC-MODEL lines and XC-MODELS-END, then
;;                                 either XC-NODES-ERROR <detail> or XC-NODE
;;                                 lines and XC-NODES-END
;;
;; Every state but `pairs` is a failure.

(require '[clojure.java.io :as io]
         '[clojure.string :as str])

(import '[java.time ZonedDateTime])

(def ^:private args *command-line-args*)
(def ^:private at-literal (nth args 0))
(def ^:private policy (nth args 1))
(def ^:private api-ns (symbol (nth args 2)))
(def ^:private other-nss (map symbol (drop 3 args)))

;; Every var this probe resolves in api-ns. Checked before any is called, so a
;; missing one is named rather than discovered as a nil deref.
(def ^:private required-vars
  '[enumerate-pairs enumerate identity-tuple node rate-plans-iri rate-plans-name
    one-modifier-at-most named-versions-add repeated-ids-refuse prepare])

(defn- emit [state detail]
  (println (str "XC-STATE " state (when detail (str " " detail))))
  (flush)
  (System/exit 0))

(defn- root-cause [^Throwable t]
  (if-let [c (.getCause t)] (recur c) t))

(defn- one-line [^Throwable t]
  (let [rc (root-cause t)]
    (str/replace (str (.getName (class rc)) ": " (.getMessage rc)) #"\s*\n\s*" " / ")))

;; Absent and broken, distinguished two ways rather than one, because each way
;; alone has a false negative. The resource lookup alone would call an
;; AOT-compiled or otherwise sourceless namespace absent. The require alone
;; would call a namespace whose OWN require of a missing dependency threw
;; absent, which is the dangerous direction: that is a broken release reading
;; as a missing one. So: absent requires BOTH that no source or class resource
;; exists AND that the throw is a FileNotFoundException naming this very
;; namespace. Anything else that throws is present and broken.
(defn- ns-path [ns-sym]
  (-> (str ns-sym) (str/replace "-" "_") (str/replace "." "/")))

(defn- resource-present? [ns-sym]
  (let [base (ns-path ns-sym)]
    (boolean (some io/resource [(str base ".clj") (str base ".cljc") (str base "__init.class")]))))

(defn- self-not-found? [ns-sym ^Throwable t]
  (let [rc (root-cause t)]
    (and (instance? java.io.FileNotFoundException rc)
         (str/includes? (or (.getMessage rc) "") (ns-path ns-sym)))))

(defn- load-ns
  "nil when ns-sym loaded, :absent when it is not on the classpath, or the
   Throwable loading it threw."
  [ns-sym]
  (let [outcome (try (require ns-sym) nil (catch Throwable t t))]
    (cond
      (nil? outcome) nil
      (and (not (resource-present? ns-sym)) (self-not-found? ns-sym outcome)) :absent
      :else outcome)))

(let [outcome (load-ns api-ns)]
  (cond
    (nil? outcome) nil
    (= :absent outcome)
    (if-let [s (first (filter #(nil? (load-ns %)) other-nss))]
      (emit "ns-renamed" (str s))
      (emit "ns-absent" (str/join "," (map str (cons api-ns other-nss)))))
    :else (emit "ns-load-error" (one-line outcome))))

(let [missing (remove #(ns-resolve api-ns %) required-vars)]
  (when (seq missing)
    (emit "ns-present-var-absent"
          (str api-ns " lacks " (str/join ", " missing) "; it interns "
               (count (ns-publics api-ns)) " public vars: "
               (str/join ", " (sort (map str (keys (ns-publics api-ns)))))))))

(def ^:private f (ns-resolve api-ns 'enumerate-pairs))

;; The corpus, as documents, through urpx.load/documents: load-graph mapcat'd,
;; expand-document-entities, coerce-doc kept, in place of composing those by
;; hand, which an earlier version of this probe got wrong in the way that
;; returns a plausible number rather than an error. Since
;; clj-urpx 0.36.0 it also yields each urpx:URPXPackage as a SHELL, its own
;; properties with every payload replaced by a reference, which is how a zone
;; declared only on a package reaches the enumerator under :package-zones.
(def ^:private paths
  (try
    (require 'urpx-rate-plans)
    ;; Filings withheld from resolution (dev/withheld-filings.json) are left
    ;; out here as dev/scenario_cost_models.py leaves them out of every
    ;; composition, so both sides enumerate over the same bases.
    (vec (remove #((resolve 'urpx-rate-plans/withheld?) "." %)
                 ((resolve 'urpx-rate-plans/paths) ".")))
    (catch Throwable t (emit "documents-error" (one-line t)))))

(def ^:private documents
  (try
    (when (empty? paths)
      (emit "documents-error" "no filing JSON-LD under us/"))
    (require 'urpx.load)
    (let [load-docs (resolve 'urpx.load/documents)]
      (when-not load-docs
        (emit "documents-error" "pinned clj-urpx lacks urpx.load/documents"))
      (let [docs (load-docs paths)]
        (when (empty? docs)
          (emit "documents-error"
                (str (count paths) " filing path(s) yielded zero coerced documents")))
        docs))
    (catch Throwable t (emit "documents-error" (one-line t)))))

;; ALL FIVE PARAMETERS ARE STATED, none defaulted, because matching on a default
;; is agreement by coincidence rather than by assertion. :repeated-ids and
;; :package-zones decide what is read, so they are given once to `prepare`; the
;; other three go to each call. What each one is doing, and what it costs:
;;
;;   :at             the pinned instant. A scenario cost model is current when every
;;                   component is, so a pair count is a property of the corpus
;;                   AT A TIME. Two sides both drifting to "now" can agree while
;;                   both answering a different question.
;;
;;   :combine        one-modifier-at-most. A CALLER policy: nothing in URPX
;;                   states exclusivity or combinability between modifiers.
;;                   Knowingly incomplete, since real multi-overlay compositions
;;                   exist.
;;
;;   :compatibility  named-versions-add. Whether stating
;;                   applicableToRatePlanVersion NARROWS the compatibility
;;                   applicableToRatePlan asserts, or ADDS to it.
;;
;;                   URPX Decision #090 introduced the property and is the only
;;                   artifact evidence either implementation has found. IT
;;                   SUPPORTS BOTH READINGS, a few lines apart, so both halves
;;                   are quoted here rather than the half that suits this pin.
;;
;;                   For ADD, from its Impact Assessment and its selected
;;                   alternative: "Breaking Change: None - this is an additive
;;                   enhancement", and it "Preserves the existing document-level
;;                   properties for document-scoped relationships". The second
;;                   is the stronger half, because it is about meaning; the
;;                   first is a conformance claim, and adding an optional
;;                   property cannot invalidate an existing document either way.
;;
;;                   For NARROW, from its Rationale: the new properties "avoid
;;                   ambiguity where a modifier document is broadly applicable
;;                   but only certain modifier versions are valid for a
;;                   particular rate plan version". Broadly applicable, only
;;                   certain valid, is narrowing described.
;;
;;                   The honest cost of add: under it this property can never
;;                   change an answer that applicableToRatePlan did not already
;;                   license, so a decision taken to add precision buys almost
;;                   none. That is a real argument against this pin and it is
;;                   recorded here rather than left out.
;;                   The honest cost of narrow: it is non-monotonic. Merging a
;;                   document can retract a compatibility that held before it,
;;                   which RDF merge never does.
;;
;;                   THERE ARE THREE READINGS, NOT TWO, and the Rationale
;;                   sentence above is about the third. It restricts which
;;                   MODIFIER versions pair with a given base version, which is
;;                   the mirror property hasModifierVersionOptions doing its
;;                   job, and says nothing about whether naming a version of one
;;                   plan withdraws a modifier from the other plans it names.
;;                   So: (a) add, retracting nothing; (b) narrow within a plan
;;                   whose version is named, leaving unnamed plans whole; (c)
;;                   fully exhaustive, retracting everything unnamed. Our
;;                   enumerator implemented (c) until it was aligned to (a).
;;                   Nothing in #090 argues for (c), and the preserves-
;;                   document-level line argues against it specifically.
;;
;;                   clj-urpx CONFIRMED ITS named-versions-narrow IS (c), by
;;                   test on their side: a modifier naming plans P and Q with
;;                   one version of P, asked about Q's version, returns [].
;;                   Their default was (c) through clj-urpx 0.47.0 and is (a)
;;                   from 0.48.0, matching this pin.
;;                   (b) is not shipped by either of us; their policy signature
;;                   receives version @ids as strings and cannot tell which plan
;;                   each belongs to, so (b) needs a richer signature rather
;;                   than another function.
;;
;;                   THIS CORPUS DISTINGUISHES NONE OF THE THREE. The one node
;;                   that separated (a) from (c), a copy of
;;                   cpau:e-nse-1-2025-09-01 naming one version of one of the
;;                   three plans it applied to, was a copy-local artifact and
;;                   was removed. (a) and (b) differ only when a modifier names
;;                   version(s) of a plan without naming that plan's current
;;                   version, and that occurs zero times here. So this pin
;;                   asserts a reading; it is not a measurement this corpus can
;;                   falsify, and a green gate is not evidence for it. The
;;                   discriminating fixtures live in dev/test_scenario_cost_models.py.
;;
;;                   Filed for the working group: the decision text supports
;;                   both readings and neither implementation can settle it by
;;                   implementing one.
;;
;;   :repeated-ids   repeated-ids-refuse, which is clj-urpx's own default.
;;                   A repeated version @id means one IRI names more than one
;;                   snapshot, and refusing is the honest answer: union merges
;;                   the two property by property and yields a node no filing
;;                   contains. This was repeated-ids-union while three such @ids
;;                   existed. All three are now gone: cpau:e-1-2025-07-01 and
;;                   cpau:e-eec-1-2025-09-01 when the pre-composed CPAU E-1
;;                   bundle was deleted, and cpau:e-nse-1-2025-09-01 with the
;;                   copy-local property above. Under refuse a new one fires
;;                   here instead of being silently merged, which is the point.
;;
;;   :package-zones  :agree, clj-urpx's own default. A urpx:timezoneIdentifier
;;                   on a package is one more declaration, which must agree
;;                   with the version's, its identity's and its document's.
;;                   Our side reads no zone to enumerate, so this pin can only
;;                   refuse (:conflicting-timezone), never move a pair.
;;
;; Our side resolves a repeated @id by AUTHORITY, the definition in the version's
;; own filing, which is a corpus-layout rule no library can implement. With no
;; repeated @ids left, the two sides agree without either rule being exercised.
;; If that ever stops holding, this gate fires, which is what it is for.

;; The corpus read once, under the two read-time policies, for enumerate-pairs
;; and enumerate below.
(def ^:private prepared
  (try
    ((ns-resolve api-ns 'prepare)
     documents
     {:repeated-ids  @(ns-resolve api-ns 'repeated-ids-refuse)
      :package-zones :agree})
    (catch Throwable t (emit "call-error" (one-line t)))))

(def ^:private opts
  {:at            (ZonedDateTime/parse at-literal)
   :combine       @(ns-resolve api-ns 'one-modifier-at-most)
   :compatibility @(ns-resolve api-ns 'named-versions-add)})

(def ^:private result
  (try (f prepared opts)
       (catch Throwable t (emit "call-error" (one-line t)))))

(defn- shape-error [r]
  (cond
    (nil? r) "returned nil"
    (not (coll? r)) (str "returned " (.getName (class r)) ", not a collection")
    :else
    (first (keep (fn [item]
                   (cond
                     (not (sequential? item)) (str "element is not a pair: " (pr-str item))
                     (not= 2 (count item)) (str "element is not a 2-tuple: " (pr-str item))
                     (not (string? (first item))) (str "pair's base is not a string IRI: " (pr-str item))
                     (not (coll? (second item))) (str "pair's modifier set is not a collection: " (pr-str item))
                     (not (every? string? (second item))) (str "pair's modifier set holds a non-string: " (pr-str item))
                     :else nil))
                 r))))

(when-let [err (shape-error result)]
  (emit "shape-error" err))

(println "XC-STATE pairs")
(doseq [[base mods] (sort-by (fn [[b m]] [b (vec (sort m))]) (vec result))]
  (println (str "XC-PAIR\t" base "\t" (str/join "," (sort mods)))))
(println (str "XC-END " (count (set (map (fn [[b m]] [b (set m)]) result)))))
(flush)

;; The same instant and policies, with open dimensions expanded: one model per
;; selection, each printed as its identity-tuple, which is the form
;; dev/scenario_cost_models.py identifies a scenario cost model by.
(def ^:private models
  (try ((ns-resolve api-ns 'enumerate) prepared opts)
       (catch Throwable t
         (println (str "XC-MODELS-ERROR " (one-line t)))
         (flush)
         (System/exit 0))))

(let [identity-tuple (ns-resolve api-ns 'identity-tuple)
      rows (sort (map (fn [m]
                        (let [[base mods alts] (identity-tuple m)]
                          (str base "\t" (str/join "," mods) "\t" (str/join "," alts))))
                      models))]
  (doseq [r rows] (println (str "XC-MODEL\t" r)))
  (println (str "XC-MODELS-END " (count models))))
(flush)

;; Each model as the urpx:ScenarioCostModel node clj-urpx builds, its @id minted
;; by rate-plans-iri and its urpx:name by rate-plans-name, clj-urpx's
;; implementations of this repository's IRI and name rules, and written by
;; urpx.emit with no @context. Compact @ids are expanded through
;; the corpus filings' own @contexts, not through the report's, so the node is
;; built from nothing this repository emitted. The caller compares each against
;; the node reports/scenario-cost-models.jsonld carries for the same identity.
(try
  (require 'urpx.emit)
  (let [node    (ns-resolve api-ns 'node)
        iri-fn  @(ns-resolve api-ns 'rate-plans-iri)
        write   (resolve 'urpx.emit/write-scenario-cost-model)
        read    (requiring-resolve 'clojure.data.json/read-str)
        context (vec (distinct (keep #(get (read (slurp %)) "@context") paths)))
        name-fn @(ns-resolve api-ns 'rate-plans-name)
        lines   (sort (map #(write (node % iri-fn {:context context :name (name-fn %)}) {:context nil})
                           models))]
    (doseq [l lines] (println (str "XC-NODE\t" l)))
    (println (str "XC-NODES-END " (count lines))))
  (catch Throwable t (println (str "XC-NODES-ERROR " (one-line t)))))
(flush)
(System/exit 0)
