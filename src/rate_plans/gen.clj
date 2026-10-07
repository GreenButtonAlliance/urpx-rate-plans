;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: CDLA-Permissive-2.0
(ns rate-plans.gen
  "The generator. Loads every namespace corpus.json lists as clojure-source,
   then writes each version of each :rate-plans.kind/document defined in them
   to <out>/<corpus path>, printing each path relative to <out>.

     clojure -M:generate [out]

   <out> defaults to a new temporary directory, named on stderr.
   dev/check_generated.py compares the output with the committed documents by
   RDF hash; with --write it writes into the working tree each document that
   is new or differs."
  (:require [clojure.java.io :as io]
            [clojure.string :as str]
            [rate-plans.urpx :as u]
            [urpx-rate-plans :as layout]
            [urpx.defs :as defs])
  (:import [java.nio.file Files]
           [java.nio.file.attribute FileAttribute]))

(defn- path->ns
  "src/rate_plans/us/wa/scl/rts.clj -> rate-plans.us.wa.scl.rts: the path
   below its root directory, by the namespace-to-path rule."
  [path]
  (-> path
      (str/replace-first #"^[^/]+/" "")
      (str/replace #"\.clj$" "")
      (str/replace "/" ".")
      (str/replace "_" "-")
      symbol))

(defn load-source!
  "Require every clojure-source namespace under repository `root`; return
   their symbols."
  [root]
  (let [nses (map path->ns
                  (layout/paths root ["clojure-source"]))]
    (run! require nses)
    nses))

(defn document-path
  "The corpus path, relative to the repository root, of the version of
   document `doc` effective on `date`."
  [{:keys [kind schedule utility]} date]
  (let [stem (case kind
               :rate-plan "rate-plan"
               :rate-plan-modifier "rate-plan-modifier")]
    (str/join "/"
              (concat (:path utility)
                      [schedule
                       "versions"
                       date
                       (str stem "_" (:key utility) "_" schedule "_" date ".jsonld")]))))

(defn generate
  "Write every version of every document defined in `nses` under `out`;
   return the paths written, relative to `out`."
  [nses out]
  (doall
   (for [doc-var (defs/defs-of-kind :rate-plans.kind/document nses)
         :let [{:keys [versions expand utility] :as doc} @doc-var]
         [date next] (u/version-dates versions)]
     (let [rel (document-path doc date)]
       (u/write! (expand doc date next)
                 (u/context (:prefix utility))
                 (io/file out rel))
       rel))))

(defn -main [& [out]]
  (let [out (or out
                (let [d (str (Files/createTempDirectory "rate-plans-gen"
                                                        (make-array FileAttribute 0)))]
                  (binding [*out* *err*]
                    (println "writing to" d))
                  d))]
    (run! println
          (sort (generate (load-source! ".")
                          out)))
    (shutdown-agents)))
