;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: CDLA-Permissive-2.0
(ns shacl-gate
  "SHACL-validate the corpus against a pinned URPX revision, with
   com.dcj/clj-shacl (Apache Jena SHACL).

   The gate unit is a MERGED graph per utility, not a per-file run.
   Cross-file references (urpx:applicableToRatePlan, urpx:supersedes) only
   resolve when the referent is in the same graph, and no modifier pairing
   crosses a utility boundary, so merging one utility resolves every reference
   it has.

   As with pyshacl given an ontology, the ontology's RDFS and OWL axioms
   (shacl.core/inoculate) are mixed into a copy of the data before validating.
   The refusal check and the shape exceptions read the data without them.

   Modes:
     --all                every utility, each as its own merged graph
     --utility <slug>     one utility merged (the wave gate)
     --merged             the whole corpus as one graph; the only mode that
                          can see a NEW cross-utility @id collision
     --per-file           each file alone (DIAGNOSTIC: cross-file references
                          are unresolved, so failures are expected)
     <jsonld>             one file alone (DIAGNOSTIC, same caveat)

     --urpx-rev <rev>     URPX revision to validate against, in place of the
                          one each file's urpx: binding dispatches to
     --with <jsonld>      merge a derived document (repeatable) into the
                          --merged or --utility graph
     --keys               print each violation key
     --write-baseline     record every merged mode's key profile
     --check-baseline     compare every merged mode against that record
                          (add --utility <slug> to compare just one)
     --dump <spec> <out>  validate the units a JSON spec names and write
                          their raw and excepted keys as JSON (for
                          dev/check_shacl_parity.py)

   Exit codes: 0 conforming, 1 violations or a new baseline key, 2 a baseline
   key is gone (an improvement, refresh deliberately), 3 refused (no
   meaningful answer is possible, e.g. the data and the shapes share no
   vocabulary, or the URPX checkout cannot supply the revision).

   Shapes and ontology are read from the URPX checkout (URPX_CHECKOUT, else
   ../urpx) at a git revision, and are deliberately not vendored here. Every
   read happens inside one call of `run`; nothing is cached across calls, so
   a long-lived REPL answers exactly as a fresh JVM does.

   Usage: clojure -M:shacl [options], or dev/shacl.sh [options], which runs
   this in the nREPL named by .nrepl-port when one answers."
  (:require [clojure.data.json :as json]
            [clojure.java.io :as io]
            [clojure.set :as set]
            [clojure.string :as str]
            [shacl.core :as shacl]
            [urpx-rate-plans :as walker])
  (:import (java.io File)
           (java.lang ProcessBuilder$Redirect)
           (org.apache.jena.graph Graph GraphMemFactory GraphUtil Node NodeFactory Triple)
           (org.apache.jena.shacl Shapes)))

(set! *warn-on-reflection* true)

;; ---------------------------------------------------------------------------
;; Vocabulary
;; ---------------------------------------------------------------------------

(def ^:private rdf-ns "http://www.w3.org/1999/02/22-rdf-syntax-ns#")
(def ^:private sh-ns "http://www.w3.org/ns/shacl#")
(def ^:private xsd-decimal "http://www.w3.org/2001/XMLSchema#decimal")

(def old-urpx-ns "https://urpx-org.github.io/urpx/ontology/")
(def new-urpx-ns "https://urpx.org/ns/ontology/")

(defn- iri ^Node [s] (NodeFactory/createURI s))

(def ^:private rdf-type (iri (str rdf-ns "type")))
(def ^:private sh-path (iri (str sh-ns "path")))

(defn- urpx ^Node [local] (iri (str new-urpx-ns local)))

(def shapes-path "shacl/urpx-shacl.ttl")
(def ontology-path "ontology/urpx-ontology.ttl")

;; ---------------------------------------------------------------------------
;; Output and refusal
;; ---------------------------------------------------------------------------

(defn- err
  [& xs]
  (binding [*out* *err*]
    (apply println xs)))

(defn- refuse!
  "Abort the run with exit 3 and `msg` on stderr."
  [msg]
  (throw (ex-info msg {::refused true})))

;; ---------------------------------------------------------------------------
;; The URPX checkout at a revision
;; ---------------------------------------------------------------------------

;; Git exports these to hooks; in a linked worktree GIT_DIR names this
;; repository's worktree git dir, and `git -C <URPX checkout>` would look there.
;; The URPX checkout is a different repository, located from its own path.
(def ^:private repo-locating-git-vars
  ["GIT_DIR" "GIT_WORK_TREE" "GIT_INDEX_FILE" "GIT_COMMON_DIR"
   "GIT_OBJECT_DIRECTORY" "GIT_ALTERNATE_OBJECT_DIRECTORIES" "GIT_PREFIX"])

(defn- urpx-git
  "Run git in `checkout`. Returns {:exit int :out bytes}."
  [checkout & args]
  (let [pb (ProcessBuilder. ^java.util.List (into ["git" "-C" (str checkout)] args))
        env (.environment pb)]
    (doseq [v repo-locating-git-vars]
      (.remove env v))
    (.redirectError pb ProcessBuilder$Redirect/DISCARD)
    (let [p (.start pb)
          out (.readAllBytes (.getInputStream p))]
      {:exit (.waitFor p)
       :out out})))

(defn- read-at-rev
  "The bytes of `rel-path` in the URPX checkout at `rev`.

   `git show <rev>:<path>` has been unreliable for the multi-megabyte SHACL
   blob, so this falls back to resolving the blob hash and cat-file-ing it."
  ^bytes [^File checkout rev rel-path]
  (when-not (.exists (io/file checkout ".git"))
    (refuse! (str "ERROR: no URPX checkout at " checkout ". The shapes are read from it "
                  "at a pinned revision and are deliberately not vendored here. Clone "
                  "urpx-org/urpx next to this repository, or set URPX_CHECKOUT to an "
                  "existing clone.")))
  (let [shown (urpx-git checkout "show" (str rev ":" rel-path))]
    (if (zero? (:exit shown))
      (:out shown)
      (let [ls (urpx-git checkout "ls-tree" rev rel-path)
            fields (str/split (str/trim (String. ^bytes (:out ls) "UTF-8")) #"\s+")]
        (cond
          (not (zero? (:exit ls)))
          (refuse! (str "ERROR: revision '" rev "' is unknown in " checkout ". If it is a "
                        "new tag or branch, fetch it first:  git -C " checkout
                        " fetch --all --tags"))

          (< (count fields) 3)
          (refuse! (str "ERROR: " rel-path " does not exist in " checkout " at revision "
                        rev ". The URPX repository layout may have changed at that release."))

          :else
          (:out (urpx-git checkout "cat-file" "-p" (nth fields 2))))))))

(defn context
  "Everything one run reads, memoized for that run only. `env` supplies
   URPX_CHECKOUT, the caller's rather than this JVM's when they differ."
  ([root] (context root (System/getenv)))
  ([^File root env]
   (let [checkout (io/file (or (get env "URPX_CHECKOUT")
                               (io/file (.getParentFile root) "urpx")))
         turtle (memoize (fn [rev rel-path]
                           (shacl/read-turtle (read-at-rev checkout rev rel-path))))
         shapes-graph (fn [rev] (turtle rev shapes-path))
         ontology (fn [rev] (turtle rev ontology-path))]
     {:root root
      :shapes-graph shapes-graph
      :shapes (memoize (fn [rev] (Shapes/parse ^Graph (shapes-graph rev))))
      :inoculated (memoize (fn [rev] (shacl/inoculate (ontology rev))))})))

;; ---------------------------------------------------------------------------
;; Corpus
;; ---------------------------------------------------------------------------

(defn- rel
  [^File root ^File f]
  (str (.relativize (.toPath (.getCanonicalFile root)) (.toPath (.getCanonicalFile f)))))

(defn utility-of
  "The utility slug of a filing path, anchored on its `versions` segment."
  [^File root ^File f]
  (let [parts (str/split (rel root f) #"/")
        i (.indexOf ^java.util.List parts "versions")]
    (when (or (< i 3) (>= (inc i) (count parts)))
      (refuse! (str "REFUSED  not inside a filing directory: " f)))
    (nth parts (- i 3))))

(defn corpus-files
  "Every rate-plan filing, optionally narrowed to one utility."
  ([root] (corpus-files root nil))
  ([root utility]
   (let [files (walker/sources root)]
     (when (empty? files)
       (refuse! "REFUSED  corpus discovery found no rate-plan filings."))
     (cond->> files
       utility (filterv #(= utility (utility-of root %)))))))

(defn utilities
  [root]
  (vec (sort (set (map #(utility-of root %) (corpus-files root))))))

;; ---------------------------------------------------------------------------
;; Version dispatch
;; ---------------------------------------------------------------------------
;; During a migration the corpus can carry two vocabularies at once. Each file
;; declares its own through its @context urpx binding, and the shape revision
;; is selected from that. A mixed-vocabulary set is refused rather than
;; validated against either shape set, which would exempt half the files.

(def urpx-namespace-revs
  {old-urpx-ns "v0.2.1"
   new-urpx-ns "v0.5.1"})

(defn declared-namespace
  "The urpx: binding a file declares in its @context, without parsing RDF."
  [f]
  (let [ctx (get (json/read-str (slurp f)) "@context")]
    (cond
      (map? ctx) (get ctx "urpx")
      (sequential? ctx) (some #(when (and (map? %) (contains? % "urpx")) (get % "urpx")) ctx)
      :else nil)))

(defn dispatch-rev
  "[revision error]. Refuses a mixed-vocabulary file set."
  [files]
  (let [seen (group-by #(str (declared-namespace %)) files)]
    (if (> (count seen) 1)
      [nil (str "mixed URPX vocabularies in one graph:\n"
                (str/join "\n" (for [[ns fs] (sort-by key seen)]
                                 (str "    " ns "  (" (count fs) " file(s))")))
                "\n    Validating a mixed set against either shape set would exempt "
                "half the files. Migrate a whole utility at a time.")]
      (let [ns (key (first seen))]
        (if-let [rev (get urpx-namespace-revs ns)]
          [rev nil]
          [nil (str "unknown urpx namespace '" ns "'; no shape revision is mapped to it")])))))

;; ---------------------------------------------------------------------------
;; Shape exceptions for proposed URPX terms (dev/shape-exceptions.json)
;; ---------------------------------------------------------------------------
;; A filing may use a term proposed in an open urpx-org/urpx pull request ahead
;; of any release. At a shape revision without that proposal the corpus fails on
;; exactly the results the proposal's own shape changes would remove. The table
;; names those results; the focus tests below decide which nodes qualify, and
;; read the data graph alone, never the ontology.

(defn- objects
  [^Graph g ^Node s ^Node p]
  (mapv #(.getObject ^Triple %) (iterator-seq (.find g s p Node/ANY))))

(defn- has?
  [^Graph g ^Node s ^Node p]
  (.contains g s p Node/ANY))

(defn- typed?
  [^Graph g ^Node node local]
  (.contains g node rdf-type (urpx local)))

(defn- decimal-literal?
  [^Node n]
  (and (.isLiteral n) (= xsd-decimal (.getLiteralDatatypeURI n))))

(defn- adjusting-bracket?
  "A bracket urpx-org/urpx#80's shapes admit: exactly one
   urpx:adjustsServiceTier naming a urpx:ServiceTier that hosts no adjusting
   bracket itself, at least one offset, each offset single and xsd:decimal,
   and no bound or bound operator (the fourth sh:or branch)."
  [^Graph g node]
  (let [targets (distinct (objects g node (urpx "adjustsServiceTier")))
        offsets (mapv #(objects g node (urpx %)) ["lowerBoundOffset" "upperBoundOffset"])]
    (boolean
     (and (typed? g node "ServiceBracket")
          (= 1 (count targets))
          (typed? g (first targets) "ServiceTier")
          (not-any? #(has? g % (urpx "adjustsServiceTier"))
                    (objects g (first targets) (urpx "hasServiceBracket")))
          (some seq offsets)
          (not-any? #(> (count %) 1) offsets)
          (every? decimal-literal? (apply concat offsets))
          (not-any? #(has? g node (urpx %))
                    ["lowerBound" "lowerBoundOperator" "upperBound" "upperBoundOperator"])))))

(defn- host-tier?
  "A tier #80's second ServiceTier branch admits: no urpx:serviceTierNumber,
   and only adjusting brackets, at least one of them."
  [^Graph g node]
  (let [brackets (objects g node (urpx "hasServiceBracket"))]
    (boolean
     (and (typed? g node "ServiceTier")
          (not (has? g node (urpx "serviceTierNumber")))
          (seq brackets)
          (every? #(adjusting-bracket? g %) brackets)))))

(defn- bounds-only-billing-model?
  "A billing model #80's BillingModelShape admits without a price definition:
   one hosting an adjusting bracket."
  [^Graph g node]
  (boolean
   (and (typed? g node "BillingModel")
        (not (has? g node (urpx "hasPriceDefinition")))
        (some #(adjusting-bracket? g %)
              (for [sts (objects g node (urpx "hasServiceTiers"))
                    t (objects g sts (urpx "hasServiceTier"))
                    b (objects g t (urpx "hasServiceBracket"))]
                b)))))

(def focus-tests
  "The focus tests dev/shape-exceptions.json names. ServiceBracketShape's three
   branches all require a bound or forbid neither; #80 adds the branch an
   adjusting bracket satisfies, hence the node-level sh:or result."
  {"time-bracket" (fn [g node] (typed? g node "TimeBracket"))
   "adjusting-bracket" adjusting-bracket?
   "host-tier" host-tier?
   "bounds-only-billing-model" bounds-only-billing-model?})

(defn shape-exceptions
  "The table in dev/shape-exceptions.json, CURIEs expanded and each focus test
   resolved to its function. An unknown focus test refuses."
  [^File root]
  (let [table (json/read-str (slurp (io/file root "dev" "shape-exceptions.json")))
        prefixes (get table "prefixes")
        expand (fn [curie]
                 (when curie
                   (let [[p local] (str/split curie #":" 2)]
                     (if-let [ns (get prefixes p)]
                       (str ns local)
                       (refuse! (str "REFUSED  dev/shape-exceptions.json: unknown prefix in "
                                     curie))))))]
    (vec (for [e (get table "entries")]
           {:name (get e "name")
            :cites (get e "cites")
            :summary (get e "summary")
            :defines (mapv expand (get e "defines"))
            :results (vec (for [r (get e "results")
                                :let [test-name (get r "focus")]]
                            {:path (expand (get r "path"))
                             :component (expand (get r "component"))
                             :test (or (get focus-tests test-name)
                                       (refuse! (str "REFUSED  dev/shape-exceptions.json: "
                                                     "unknown focus test " test-name)))}))}))))

(defn active-exceptions
  "The entries whose terms the shapes in use do not name as an sh:path."
  [entries ^Graph shapes-graph]
  (filterv (fn [e]
             (not-any? #(.contains shapes-graph Node/ANY sh-path (iri %)) (:defines e)))
           entries))

(defn except-proposed-terms
  "[kept results, {entry name: count removed}]. A result is removed by the
   first active entry with a matching path, component and focus test."
  [entries results ^Graph data ^Graph shapes-graph]
  (let [active (active-exceptions entries shapes-graph)]
    (reduce (fn [[kept removed] r]
              (if-let [hit (first (for [e active
                                        spec (:results e)
                                        :when (and (= (:path spec) (:path r))
                                                   (= (:component spec) (:component r))
                                                   ((:test spec) data (:focus-node r)))]
                                    e))]
                [kept (update removed (:name hit) (fnil inc 0))]
                [(conj kept r) removed]))
            [[] {}]
            results)))

;; ---------------------------------------------------------------------------
;; Validation
;; ---------------------------------------------------------------------------

(defn result-key
  "The stable [focus path component] key; path is \"None\" at node level, as
   the baseline has always spelled it."
  [r]
  [(:focus r) (or (:path r) "None") (:component r)])

(defn- sorted-keys
  [results]
  (vec (sort (map result-key results))))

(defn- refused-unit
  [label msg]
  (err (str "REFUSED  " label ": " msg))
  {:status :refused :keys [] :raw-keys [] :removed {}})

(defn- union
  ^Graph [& graphs]
  (let [g (GraphMemFactory/createDefaultGraph)]
    (doseq [x graphs]
      (GraphUtil/addInto g ^Graph x))
    g))

(defn validate-graph
  "Validate `data` against the shapes at `rev`, with that revision's ontology
   mixed into a copy of it. Returns {:report :kept :removed}; the exceptions
   are tested against `data` alone."
  [ctx rev ^Graph data exceptions]
  (let [report (shacl/validate (union data ((:inoculated ctx) rev)) ((:shapes ctx) rev))
        [kept removed] (except-proposed-terms exceptions (:results report) data
                                              ((:shapes-graph ctx) rev))]
    {:report report
     :kept kept
     :removed removed}))

(defn validate-files
  "Validate `files` as ONE merged graph. Returns {:status (:ok, :violations or
   :refused) :keys :raw-keys :removed :rev}.

   `extra` documents are merged in after dispatch, so a derived document is
   held to the corpus's shape revision (or `rev-override`). One that adds no
   triple is refused: merging nothing would report the corpus's conformance as
   the derived document's."
  [ctx files label {:keys [verbose? show-keys? rev-override extra exceptions]}]
  (let [[dispatched dispatch-err] (when (seq files) (dispatch-rev (concat files extra)))]
    (cond
      (empty? files)
      (refused-unit label (str "no filings matched. Corpus discovery is broken or the "
                               "selector is wrong; refusing to report conformance over an "
                               "empty graph."))

      dispatch-err
      (refused-unit label dispatch-err)

      :else
      (let [rev (or rev-override dispatched)
            data (shacl/read-jsonld (map str files))
            empty-extra (some (fn [f]
                                (let [before (.size data)]
                                  (GraphUtil/addInto data (shacl/read-jsonld [(str f)]))
                                  (when (= before (.size data)) f)))
                              extra)
            shapes-graph ((:shapes-graph ctx) rev)]
        (cond
          empty-extra
          (refused-unit label (str empty-extra " adds no triple to the graph."))

          (not (shacl/targets-any? data shapes-graph))
          (refused-unit label (str "no shape targets any class asserted in these "
                                   (count files) " file(s) at URPX " rev ". Validation "
                                   "would pass vacuously. Check the urpx: namespace binding "
                                   "against the pinned revision, or pass --urpx-rev."))

          :else
          (let [{:keys [report kept removed]} (validate-graph ctx rev data exceptions)
                conforms? (if (seq removed) (empty? kept) (:conforms? report))
                ks (sorted-keys kept)]
            (when verbose?
              (doseq [e exceptions
                      :let [n (get removed (:name e))]
                      :when n]
                (println (str "EXCEPT  " label ": " n " result(s) for " (:summary e)
                              ", under " (:name e) " (" (:cites e) ")")))
              (let [n (str (count files) " files"
                           (when (seq extra) (str " + " (count extra) " derived")))]
                (if conforms?
                  (println (str "PASS  " label "  (" n ", URPX " rev ")"))
                  (do (println (str "FAIL  " label "  (" n ", URPX " rev ", " (count ks)
                                    " violations)"))
                      (when show-keys?
                        (doseq [[focus path comp] ks]
                          (println (str "  " focus " | " path " | "
                                        (last (str/split comp #"#"))))))))))
            {:status (if conforms? :ok :violations)
             :keys ks
             :raw-keys (sorted-keys (:results report))
             :removed removed
             :rev rev}))))))

(def ^:private status-exit {:ok 0 :violations 1 :refused 3})

;; ---------------------------------------------------------------------------
;; Baseline (dev/baseline/corpus.json)
;; ---------------------------------------------------------------------------

(defn- py-json-string
  "A string as Python's json.dumps writes it (ensure_ascii)."
  [^String s]
  (let [sb (StringBuilder. "\"")]
    (doseq [c s]
      (case c
        \" (.append sb "\\\"")
        \\ (.append sb "\\\\")
        \newline (.append sb "\\n")
        \return (.append sb "\\r")
        \tab (.append sb "\\t")
        \backspace (.append sb "\\b")
        \formfeed (.append sb "\\f")
        (if (or (< (int c) 0x20) (> (int c) 0x7e))
          (.append sb (format "\\u%04x" (int c)))
          (.append sb c))))
    (str (.append sb "\""))))

(defn- py-json
  "`x` as Python's json.dumps(x, indent=2, sort_keys=True) writes it, so a
   baseline written by either engine is byte-identical."
  ([x] (py-json x 0))
  ([x level]
   (let [pad (apply str (repeat (* 2 (inc level)) \space))
         end (apply str (repeat (* 2 level) \space))]
     (cond
       (map? x) (if (empty? x)
                  "{}"
                  (str "{\n"
                       (str/join ",\n" (for [[k v] (sort-by (comp str key) x)]
                                         (str pad (py-json-string (str k)) ": "
                                              (py-json v (inc level)))))
                       "\n" end "}"))
       (sequential? x) (if (empty? x)
                         "[]"
                         (str "[\n"
                              (str/join ",\n" (for [v x] (str pad (py-json v (inc level)))))
                              "\n" end "]"))
       (string? x) (py-json-string x)
       (nil? x) "null"
       :else (str x)))))

(defn- baseline-file
  ^File [root]
  (io/file root "dev" "baseline" "corpus.json"))

(defn- merged
  [ctx files label opts]
  (validate-files ctx files label (assoc opts :verbose? false)))

(defn collect-modes
  "Every merged mode's key profile, or nil when one refuses. The whole-corpus
   mode is recorded as unavailable while the corpus carries two vocabularies;
   any other refusal aborts."
  [ctx opts]
  (let [root (:root ctx)
        [_ mixed-err] (dispatch-rev (corpus-files root))
        corpus-mode (if (and mixed-err (str/starts-with? mixed-err "mixed"))
                      {"unavailable" "mixed vocabularies during migration"}
                      (let [{:keys [status keys]} (merged ctx (corpus-files root)
                                                          "corpus (merged)" opts)]
                        (when-not (= :refused status)
                          {"count" (count keys) "keys" keys})))]
    (when corpus-mode
      (reduce (fn [modes u]
                (let [{:keys [status keys]} (merged ctx (corpus-files root u)
                                                    (str u " (merged)") opts)]
                  (if (= :refused status)
                    (reduced nil)
                    (assoc modes u {"count" (count keys) "keys" keys}))))
              {"corpus" corpus-mode}
              (utilities root)))))

(defn- subject-index
  "Every subject IRI to the set of files asserting it."
  [root]
  (reduce (fn [idx f]
            (let [r (rel root f)
                  g ^Graph (shacl/read-jsonld [(str f)])]
              (reduce (fn [idx ^Triple t]
                        (let [s (.getSubject t)]
                          (if (.isURI s)
                            (update idx (.getURI s) (fnil conj #{}) r)
                            idx)))
                      idx
                      (iterator-seq (.find g Node/ANY Node/ANY Node/ANY)))))
          {}
          (corpus-files root)))

(def ^:private baseline-note
  (str "Accepted violations at this URPX revision. Compared as SETS, not "
       "counts: a count is invariant under one violation being traded for "
       "another, which is what a migration produces. Per-file mode is "
       "excluded because its keys are not comparable. "
       "The 'cross-filing-iri-reuse' triage counts focus nodes asserted in "
       "more than one file. What that means changed once subordinate @ids "
       "were scoped to their owning version: it no longer covers one "
       "descriptor minted by several schedules (dev/lint_iri_scope.py now "
       "refuses that outright), and every remaining key is a node DEFINED "
       "twice, which is a different defect tracked separately."))

(defn write-baseline
  [ctx opts]
  (let [root (:root ctx)
        modes (collect-modes ctx opts)]
    (if-not modes
      (do (err "REFUSED  cannot record a baseline the harness would not report.")
          3)
      (let [idx (subject-index root)
            triage-keys (if (contains? (get modes "corpus") "keys")
                          (get-in modes ["corpus" "keys"])
                          (vec (sort (set (for [[m d] modes
                                                :when (not= m "corpus")
                                                k (get d "keys")]
                                            k)))))
            single? #(<= (count (get idx (first %))) 1)
            triage (cond-> {}
                     (seq (remove single? triage-keys))
                     (assoc "cross-filing-iri-reuse" (count (remove single? triage-keys)))
                     (seq (filter single? triage-keys))
                     (assoc "single-file" (count (filter single? triage-keys))))
            unexplained (vec (filter single? triage-keys))
            f (baseline-file root)]
        (io/make-parents f)
        (spit f (str (py-json {"note_rev" (str "Shape revision is per-file, dispatched from "
                                               "each file's @context urpx binding.")
                               "note" baseline-note
                               "triage" triage
                               "unexplained_single_file_keys" unexplained
                               "modes" modes})
                     "\n"))
        (println (str "wrote " (rel root f)))
        (doseq [[m d] (sort-by key modes)]
          (println (if (contains? d "count")
                     (format "  %-8s %4d" m (get d "count"))
                     (format "  %-8s    - (%s)" m (get d "unavailable")))))
        (println (str "  triage: {"
                      (str/join ", " (for [[k v] triage] (str "'" k "': " v)))
                      "}"))
        (when (seq unexplained)
          (err (str "  WARNING: " (count unexplained) " key(s) whose focus node is "
                    "asserted in only one file; those are not explained by "
                    "cross-filing reuse.")))
        0))))

(defn check-baseline
  [ctx opts only]
  (let [root (:root ctx)
        f (baseline-file root)]
    (if-not (.exists f)
      (do (err (str "REFUSED  no baseline at " (rel root f) "; run --write-baseline first."))
          3)
      (let [recorded (get (json/read-str (slurp f)) "modes")
            [recorded current]
            (if only
              (if-not (contains? recorded only)
                [nil nil]
                (let [{:keys [status keys]} (merged ctx (corpus-files root only)
                                                    (str only " (merged)") opts)]
                  [{only (get recorded only)}
                   (when-not (= :refused status)
                     {only {"count" (count keys) "keys" keys}})]))
              [recorded (collect-modes ctx opts)])]
        (cond
          (and only (nil? recorded))
          (do (err (str "REFUSED  '" only "' is not a recorded mode in " (rel root f) "."))
              3)

          (nil? current)
          3

          :else
          (let [shifted (fn [[focus path comp]]
                          [focus (str/replace path old-urpx-ns new-urpx-ns) comp])
                totals
                (reduce
                 (fn [[new-n gone-n] mode]
                   (if (or (contains? (get recorded mode) "unavailable")
                           (contains? (get current mode) "unavailable"))
                     (do (println (format "SKIP %-8s unavailable (mixed vocabularies during migration)"
                                          mode))
                         [new-n gone-n])
                     ;; A migration wave moves every predicate to the new
                     ;; namespace, so each surviving violation leaves as one key
                     ;; and returns as another. Those pairs are reported as
                     ;; MIGRATED; anything that does not pair exactly stays a
                     ;; regression.
                     (let [was (set (map vec (get-in recorded [mode "keys"])))
                           now (set (map vec (get-in current [mode "keys"])))
                           added (set/difference now was)
                           removed (set/difference was now)
                           migrated (set (filter #(contains? added (shifted %)) removed))
                           added (set/difference added (set (map shifted migrated)))
                           removed (set/difference removed migrated)
                           short (fn [comp] (last (str/split comp #"#")))]
                       (println (str (format "%s %-8s baseline %4d  now %4d  +%d -%d"
                                             (if (and (empty? added) (empty? removed))
                                               "OK  "
                                               "DIFF")
                                             mode (count was) (count now)
                                             (count added) (count removed))
                                     (when (seq migrated)
                                       (str "  ~" (count migrated) " migrated"))))
                       (doseq [[focus path comp] (sort added)]
                         (println (str "      NEW      " focus " | " path " | " (short comp))))
                       (doseq [[focus path comp] (sort removed)]
                         (println (str "      RESOLVED " focus " | " path " | " (short comp))))
                       [(+ new-n (count added)) (+ gone-n (count removed))])))
                 [0 0]
                 (sort (set/union (set (keys recorded)) (set (keys current)))))
                [new-n gone-n] totals]
            (cond
              (pos? new-n)
              (do (err (str "\n" new-n " new violation key(s): regression."))
                  1)

              (pos? gone-n)
              (do (err (str "\n" gone-n " baseline key(s) no longer present: improvement. "
                            "Refresh the baseline deliberately with --write-baseline."))
                  2)

              :else
              (do (println "\nidentical to baseline")
                  0))))))))

;; ---------------------------------------------------------------------------
;; Parity dump
;; ---------------------------------------------------------------------------

(defn dump
  "Validate each unit of the JSON spec at `spec-path` ([{name, files, extra,
   rev}], paths relative to the root) and write {name: {status, rev, raw,
   kept, removed}} to `out-path`."
  [ctx opts spec-path out-path]
  (let [root ^File (:root ctx)
        file-of #(io/file root %)
        units (json/read-str (slurp spec-path))
        out (into (sorted-map)
                  (for [{:strs [files extra rev] unit-name "name"} units
                        :let [r (validate-files ctx (mapv file-of files) unit-name
                                                (assoc opts
                                                       :verbose? false
                                                       :rev-override rev
                                                       :extra (mapv file-of extra)))]]
                    [unit-name {"status" (name (:status r))
                                "rev" (:rev r)
                                "raw" (:raw-keys r)
                                "kept" (:keys r)
                                "removed" (:removed r)}]))]
    (spit out-path (json/write-str out))
    (println (str "dumped " (count out) " unit(s) to " out-path))
    0))

;; ---------------------------------------------------------------------------
;; Command line
;; ---------------------------------------------------------------------------

(def ^:private boolean-flags
  #{"--all" "--merged" "--per-file" "--rdfs" "--keys" "--write-baseline" "--check-baseline"})

(defn parse-args
  "{:flags #{...} :utility :urpx-rev :with [...] :dump [spec out] :jsonld}, or
   {:error msg}."
  [args]
  (loop [args (mapcat #(if (and (str/starts-with? % "--") (str/includes? % "="))
                         (str/split % #"=" 2)
                         [%])
                      args)
         opts {:flags #{} :with []}]
    (if-let [[a & more] (seq args)]
      (cond
        (contains? boolean-flags a) (recur more (update opts :flags conj a))
        (#{"--utility" "--urpx-rev" "--with"} a)
        (if-let [v (first more)]
          (recur (rest more)
                 (case a
                   "--utility" (assoc opts :utility v)
                   "--urpx-rev" (assoc opts :urpx-rev v)
                   "--with" (update opts :with conj v)))
          {:error (str a " needs a value")})
        (= "--dump" a)
        (if (= 2 (count (take 2 more)))
          (recur (drop 2 more) (assoc opts :dump (vec (take 2 more))))
          {:error "--dump needs a spec file and an output file"})
        (str/starts-with? a "--") {:error (str "unknown option " a)}
        (:jsonld opts) {:error (str "unexpected argument " a)}
        :else (recur more (assoc opts :jsonld a)))
      opts)))

(defn- run*
  [^File root args env]
  (let [{:keys [error flags utility urpx-rev with dump jsonld]} (parse-args args)
        flag? #(contains? flags %)
        ctx (context root env)
        abs (fn [p] (let [f (io/file p)] (if (.isAbsolute f) f (io/file root p))))
        extra (mapv abs with)
        missing (remove #(.exists ^File %) extra)
        opts {:verbose? true
              :show-keys? (flag? "--keys")
              :rev-override urpx-rev
              :exceptions (shape-exceptions root)}
        exit-of #(status-exit (:status %))]
    (cond
      error
      (do (err (str "REFUSED  " error)) 3)

      (flag? "--rdfs")
      (do (err (str "REFUSED  --rdfs: RDFS inference is not implemented on clj-shacl; "
                    "run this with URPX_SHACL_ENGINE=pyshacl dev/shacl.sh."))
          3)

      (seq missing)
      (do (err (str "REFUSED  --with names no file: " (str/join ", " missing))) 3)

      (and (seq extra) (not (or (flag? "--merged") utility)))
      (do (err "REFUSED  --with needs --merged or --utility.") 3)

      dump
      (apply shacl-gate/dump ctx opts dump)

      (flag? "--write-baseline")
      (write-baseline ctx opts)

      (flag? "--check-baseline")
      (check-baseline ctx opts utility)

      (flag? "--merged")
      (exit-of (validate-files ctx (corpus-files root) "corpus (merged)"
                               (assoc opts :extra extra)))

      utility
      (exit-of (validate-files ctx (corpus-files root utility) (str utility " (merged)")
                               (assoc opts :extra extra)))

      (flag? "--all")
      (let [names (utilities root)
            statuses (mapv #(:status (validate-files ctx (corpus-files root %)
                                                     (str % " (merged)") opts))
                           names)
            ok (count (filter #{:ok} statuses))]
        (println (str "\n" ok "/" (count names) " utilities conforming"))
        (cond
          (some #{:refused} statuses) 3
          (= ok (count names)) 0
          :else 1))

      (flag? "--per-file")
      (let [files (corpus-files root)]
        (err (str "DIAGNOSTIC: per-file mode leaves cross-file references unresolved, "
                  "so failures here are expected and are not a gate signal.\n"))
        (let [statuses (mapv #(:status (validate-files ctx [%] (rel root %) opts)) files)
              ok (count (filter #{:ok} statuses))]
          (println (str "\n" ok "/" (count files) " conforming (per-file, diagnostic)"))
          (cond
            (some #{:refused} statuses) 3
            (= ok (count files)) 0
            :else 1)))

      jsonld
      (let [f (io/file jsonld)
            f (if (and (not (.isAbsolute f)) (.exists (io/file root jsonld)))
                (io/file root jsonld)
                f)]
        (err "DIAGNOSTIC: single-file mode leaves cross-file references unresolved.")
        (exit-of (validate-files ctx [f] (rel root f) opts)))

      :else
      (do (err (str "REFUSED  give a JSON-LD path, or one of --all / --utility / --merged "
                    "/ --per-file"))
          3))))

(defn run
  "Run the SHACL step over the repository at `root` with command-line `args`
   and environment `env` (a map; URPX_CHECKOUT is the only variable read);
   returns the exit code. Every graph is read afresh by this call."
  [root args env]
  (try
    (run* (.getCanonicalFile (io/file root)) (vec args) env)
    (catch clojure.lang.ExceptionInfo e
      (cond
        (::refused (ex-data e))
        (do (err (ex-message e)) 3)

        (:url (ex-data e))
        (do (err (str "REFUSED  " (ex-message e) "; every corpus document carries its "
                      "@context inline, and nothing is fetched."))
            3)

        :else
        (throw e)))))

(defn -main
  [& args]
  (let [code (run (System/getProperty "user.dir") args (System/getenv))]
    (flush)
    (shutdown-agents)
    (System/exit code)))
