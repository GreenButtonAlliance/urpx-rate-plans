;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: CDLA-Permissive-2.0
;;
;; The clj-urpx half of dev/cross_check_arrangements.py. Run by that script,
;; never on its own:
;;
;;   clojure -M dev/cross_check_arrangements.clj <instant> <combining-policy>
;;
;; It answers one question: what does urpx.arrangements/arrangement-pairs
;; return over this corpus at that instant, and if it cannot be asked, WHY not.
;; Every answer is a single XC- line on stdout, so the caller reads a state
;; rather than inferring one from an exit code that a JVM warning could muddy.
;;
;;   XC-STATE ns-absent            the namespace is not on the classpath
;;   XC-STATE ns-load-error        it is, and loading it threw
;;   XC-STATE ns-present-var-absent it loaded, and the var is not there
;;   XC-STATE documents-error      the var is there and the corpus would not load
;;   XC-STATE call-error           the var is there and calling it threw
;;   XC-STATE shape-error          it returned something that is not a pair set
;;   XC-STATE pairs                followed by XC-PAIR lines and XC-END
;;
;; Only ns-absent is pending. Every other non-`pairs` state is a failure: the
;; var exists and the comparison did not happen, which must never read as
;; "not released yet".

(require '[clojure.java.io :as io]
         '[clojure.string :as str])

(import '[java.time ZonedDateTime])

(def ^:private args *command-line-args*)
(def ^:private at-literal (first args))
(def ^:private policy (second args))

(defn- emit [state detail]
  (println (str "XC-STATE " state (when detail (str " " detail))))
  (flush)
  (System/exit 0))

(defn- root-cause [^Throwable t]
  (if-let [c (.getCause t)] (recur c) t))

(defn- one-line [^Throwable t]
  (let [rc (root-cause t)]
    (str/replace (str (.getName (class rc)) ": " (.getMessage rc)) #"\s*\n\s*" " / ")))

;; Three states, distinguished two ways rather than one, because each way alone
;; has a false negative. The resource lookup alone would call an AOT-compiled or
;; otherwise sourceless namespace absent. The require alone would call a
;; namespace whose OWN require of a missing dependency threw absent, which is
;; the dangerous direction: that is a broken release reading as an unreleased
;; one. So: absent requires BOTH that no source or class resource exists AND
;; that the throw is a FileNotFoundException naming this very namespace.
;; Anything else that throws is present and broken.
(def ^:private resource-present?
  (boolean (some io/resource ["urpx/arrangements.clj"
                              "urpx/arrangements.cljc"
                              "urpx/arrangements__init.class"])))

(defn- self-not-found? [^Throwable t]
  (let [rc (root-cause t)]
    (and (instance? java.io.FileNotFoundException rc)
         (boolean (re-find #"urpx/arrangements(__init\.class|\.clj|\.cljc)"
                           (or (.getMessage rc) ""))))))

(def ^:private load-outcome
  (try (require 'urpx.arrangements) :loaded
       (catch Throwable t t)))

(when (instance? Throwable load-outcome)
  (if (and (not resource-present?) (self-not-found? load-outcome))
    (emit "ns-absent" nil)
    (emit "ns-load-error" (one-line load-outcome))))

(def ^:private f (resolve 'urpx.arrangements/arrangement-pairs))

(when (nil? f)
  (emit "ns-present-var-absent"
        (str "urpx.arrangements loaded and interns "
             (count (ns-publics 'urpx.arrangements)) " public vars: "
             (str/join ", " (sort (map str (keys (ns-publics 'urpx.arrangements))))))))

;; The corpus, as documents. Four steps, all load-bearing, given by the clj-urpx
;; author after an earlier three-step form of this probe was measured against
;; their enumerator and found wrong:
;;
;;   mapcat load-graph              NOT mapv. load-graph returns a VECTOR of
;;                                  top-level entities per file, so mapv yields a
;;                                  seq of vectors. That survives by accident,
;;                                  because the enumerator walks with tree-seq,
;;                                  which is why the wrong form returned a number
;;                                  rather than an error.
;;   mapcat expand-document-entities  descend a urpx:URPXPackage wrapper.
;;   keep coerce-doc                THE ONE THAT BITES. load-graph returns parsed
;;                                  but UNTYPED entities: urpx:effectiveDateTime
;;                                  is still the string "2026-03-20", not a
;;                                  LocalDateTime, so every version-window
;;                                  comparison throws ClassCastException.
;;
;; Measured by them at the pinned enumerator over this corpus: the old form with
;; no instant returned 202 pairs, a plausible wrong number rather than a
;; rejection, because with no :at their enumerator answers over the whole
;; expressed space and never touches a date, so uncoerced documents sail
;; through. With an instant it threw. The correct form gives 84 coerced docs and
;; 144 pairs.
;;
;; That failure is the same shape as the one this gate found on our side: a
;; number that agrees or disagrees for a reason unrelated to the question. They
;; are adding an uncoerced-document guard to arrangements so a future wrong form
;; is refused with a named reason rather than answered.
(def ^:private documents
  (try
    (require '[urpx.core :as core])
    (let [paths (->> (file-seq (io/file "us"))
                     (filter #(.isFile ^java.io.File %))
                     (map #(.getPath ^java.io.File %))
                     (filter #(re-matches #"us/.*/versions/[^/]+/rate-plan(?:-modifier)?_.+\.jsonld" %))
                     sort
                     vec)]
      (when (empty? paths)
        (emit "documents-error" "no filing JSON-LD under us/"))
      (require '[urpx.coerce :as coerce])
      (let [load-graph (resolve 'urpx.core/load-graph)
            expand     (resolve 'urpx.core/expand-document-entities)
            coerce-doc (resolve 'urpx.coerce/coerce-doc)]
        (when-not (and load-graph expand coerce-doc)
          (emit "documents-error"
                (str "pinned clj-urpx lacks one of the loaders this probe needs: "
                     "core/load-graph=" (some? load-graph)
                     " core/expand-document-entities=" (some? expand)
                     " coerce/coerce-doc=" (some? coerce-doc))))
        (let [docs (->> paths (mapcat load-graph) (mapcat expand) (keep coerce-doc) vec)]
          (when (empty? docs)
            (emit "documents-error"
                  (str (count paths) " filing path(s) yielded zero coerced documents")))
          docs)))
    (catch Throwable t (emit "documents-error" (one-line t)))))

;; ALL FOUR PARAMETERS ARE STATED, none defaulted, because matching on a default
;; is agreement by coincidence rather than by assertion. Three are clj-urpx
;; options; the instant is ours. What each one is doing, and what it costs:
;;
;;   :at             the pinned instant. An arrangement is current when every
;;                   component is, so a pair count is a property of the corpus
;;                   AT A TIME. Two sides both drifting to "now" can agree while
;;                   both answering a different question.
;;
;;   :combine        one-modifier-at-most. A CALLER policy: nothing in URPX
;;                   states exclusivity or combinability between modifiers.
;;                   Knowingly incomplete, since real multi-overlay arrangements
;;                   exist.
;;
;;   :compatibility  named-versions-add. Whether stating
;;                   applicableToRatePlanVersion NARROWS the compatibility
;;                   applicableToRatePlan asserts, or ADDS to it. URPX settles
;;                   neither and it is written up for the working group. Our
;;                   own enumerator narrows, but its narrowing NEVER FIRES:
;;                   4 of 37 authority-resolved modifier versions state the
;;                   property and every one names a version of the only plan it
;;                   names, so nothing is narrowed away and add and narrow are
;;                   indistinguishable on this corpus. add is stated because it
;;                   is the reading that survives RDF merge; narrow is
;;                   non-monotonic, and merging a document can retract a
;;                   compatibility under it.
;;
;;   :repeated-ids   repeated-ids-union. THIS ONE PAPERS OVER A KNOWN DEFECT and
;;                   is stated anyway, with the reason recorded here rather than
;;                   discovered later. Three version @ids in this corpus name
;;                   more than one distinct snapshot. Two of them,
;;                   cpau:e-eec-1-2025-09-01 and cpau:e-nse-1-2025-09-01, differ
;;                   only in whether applicableToRatePlanVersion is present,
;;                   which is arguably how bundled copies are written. The third,
;;                   cpau:e-1-2025-07-01, is a defect on any reading: the union
;;                   asserts that a version effective in July offered modifier
;;                   VERSIONS dated September, which did not exist on its own
;;                   effective date. Union makes it enumerable; it does not make
;;                   it true. Tracked, and a modelling question rather than an
;;                   implementation one. refuse is their default and is the
;;                   honest setting once that is resolved.
;;
;; Our side resolves a repeated @id by AUTHORITY, the definition in the version's
;; own filing, which is a corpus-layout rule no library can implement. The two
;; agree here because the authority definitions are silent on
;; applicableToRatePlanVersion. If that ever stops holding, this gate fires,
;; which is the point of it.
(def ^:private opts
  {:at            (ZonedDateTime/parse at-literal)
   :combine       @(resolve 'urpx.arrangements/one-modifier-at-most)
   :compatibility @(resolve 'urpx.arrangements/named-versions-add)
   :repeated-ids  @(resolve 'urpx.arrangements/repeated-ids-union)})

(def ^:private result
  (try (f documents opts)
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
(System/exit 0)
