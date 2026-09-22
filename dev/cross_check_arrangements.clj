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

;; The corpus, as documents. urpx.core/load-graph is the general loader (a
;; vector of top-level entities per file); load-rate-plan and
;; load-rate-plan-modifier are the narrow ones, and a base filing here bundles
;; modifiers in an @graph, so the general one is what a whole-corpus enumerator
;; wants. THIS IS OUR ASSUMPTION about what `documents` means, not something the
;; clj-urpx author stated. If arrangement-pairs rejects it, this reports
;; call-error and fails the gate: the document form then has to be settled with
;; them, and a failure saying so is the point.
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
      (mapv (resolve 'urpx.core/load-graph) paths))
    (catch Throwable t (emit "documents-error" (one-line t)))))

;; :at is passed; :combine is NOT. The documented default is base alone or base
;; plus exactly one modifier, which is the policy named on the command line, and
;; guessing the keyword their option takes would throw on a value they never
;; defined. The caller does not take our word for it either: it checks that
;; every returned pair actually obeys the policy, which holds however the option
;; is spelled.
(def ^:private opts {:at (ZonedDateTime/parse at-literal)})

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
