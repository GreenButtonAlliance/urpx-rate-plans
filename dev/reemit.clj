;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns reemit
  "Re-emit authored JSON-LD documents through the clj-urpx emitter, in
   place, with the formatting the generator writes
   (rate-plans.urpx/write!). Each top-level node is parsed and coerced
   through its urpx.schema schema; the @context written is the document's
   own over urpx.emit/default-context. The step that makes byte equality a
   fair test when a family is converted to Clojure source
   (doc/dsl-corpus-generation.md); prove the RDF unchanged with
   dev/rdf_hash.py.

     clojure -M -m reemit FILE..."
  (:require [rate-plans.urpx :as u]
            [urpx.coerce :as coerce]
            [urpx.core :as core]
            [urpx.emit :as emit]))

(defn- coerce-node
  "A parsed top-level node coerced, a package's payloads included."
  [node]
  (let [as-vec #(if (map? %) [%] %)
        c (or (coerce/coerce-doc node)
              (throw (ex-info (str "No schema for a top-level " (:jsonld/type node))
                              {:id (:jsonld/id node)})))]
    (cond-> c
      (:urpx/hasRatePlan c)
      (update :urpx/hasRatePlan #(mapv coerce/coerce-rate-plan (as-vec %)))

      (:urpx/hasRatePlanModifier c)
      (update :urpx/hasRatePlanModifier #(mapv coerce/coerce-rate-plan-modifier (as-vec %))))))

(defn reemit!
  "Rewrite the document at `path`."
  [path]
  (let [raw (core/parse-rate-plan path)
        ctx (merge emit/default-context
                   (core/keys->jsonld (:jsonld/context raw)))
        doc (if-let [g (:jsonld/graph raw)]
              (mapv coerce-node g)
              (coerce-node (dissoc raw :jsonld/context)))]
    (u/write! doc ctx path)))

(defn -main [& paths]
  (run! (comp println reemit!) paths)
  (shutdown-agents))
