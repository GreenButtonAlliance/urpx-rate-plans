;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.urpx
  "Generic URPX building blocks over urpx.dsl. Knows nothing about any
   utility."
  (:refer-clojure :exclude [ref])
  (:require [clojure.data.json :as json]
            [clojure.java.io :as io]
            [clojure.string :as str]
            [urpx.coerce :as coerce]
            [urpx.core :as core]
            [urpx.dsl :as dsl]
            [urpx.emit :as emit]
            [urpx.schema :as schema]))

(def urpx-version
  "https://github.com/urpx-org/urpx/raw/v0.5.1/ontology/urpx-ontology.ttl")

(def org-ns "https://rate-plans.grid-coordination.energy/organizations/")

(defn context
  "The @context of a utility's documents: `urpx.emit/default-context`, the
   utility's prefix, and `extra` term definitions."
  ([prefix]
   (context prefix nil))
  ([[p iri] extra]
   (merge emit/default-context
          {p iri
           "org" org-ns
           "skos" "http://www.w3.org/2004/02/skos/core#"}
          extra)))

;; A package is built in one dsl-scope: an entity is named by `:as` with a
;; keyword from `ider`, and the same keyword is a reference to it.
(defn ref
  "A reference to an entity in another document, by its CURIE."
  [curie]
  {:jsonld/id curie})

(defn ider
  "(ider :scl/rtc-2026-01-01) returns f where (f \"a\" :b) is
   :scl/rtc-2026-01-01-a-b and (f) is the base."
  [base]
  (fn [& parts]
    (keyword (namespace base)
             (str/join "-"
                       (cons (name base)
                             (map name parts))))))

(defn comparison [id op left right]
  (dsl/comparison-node
   {:as id
    :operator op
    :left-operand left
    :right-operand right}))

(defn object-comparison
  "A ComparisonNode `id` testing the URPX property `property` against the
   entity `value` with `op`; its operands are `<id>-left-operand` and
   `<id>-right-operand`."
  [id op property value]
  (let [operand (ider id)]
    (comparison id
                op
                (dsl/object-operand-node
                 {:as (operand "left-operand")
                  :condition-property property})
                (dsl/object-operand-node
                 {:as (operand "right-operand")
                  :references-value value}))))

(defn custom-comparison
  "A ComparisonNode `id` testing the custom property `property` for equality
   with `value`, given under the operand key `value-key` (:string-value,
   :g-year-value, ...)."
  [id property value-key value]
  (let [operand (ider id)]
    (comparison id
                :urpx/equalsOperator
                (dsl/custom-operand-node
                 {:as (operand "left-operand")
                  :custom-condition-property property})
                (dsl/custom-operand-node
                 {:as (operand "right-operand")
                  value-key value}))))

(defn customer-kind-rule
  "An EligibilityRule whose condition is hasCustomerKind = `kind`. The
   condition expression and its root node are named by `:cx` and `:cn`
   (default `<id>-condition-expression` and
   `<id>-condition-expression-root-node`)."
  [id {:keys [name description customer-kind cx cn]}]
  (let [cx (or cx (id "condition-expression"))]
    (dsl/eligibility-rule
     {:as (id)
      :name name
      :description description
      :has-condition-expression
      (dsl/condition-expression
       {:as cx
        :root-node (object-comparison (or cn ((ider cx) "root-node"))
                                      :urpx/equalsOperator
                                      :urpx/hasCustomerKind
                                      customer-kind)})})))

(defn utility-operator [{:keys [key legal-name eia-id]}]
  (let [o (keyword "org" (str "utility-" key))
        id (ider o)]
    (dsl/utility-operator
     {:as o
      :legal-name legal-name
      :organization-type :urpx/utilityOrganization
      :has-identity
      (dsl/organization-identity
       {:as (id "identity")
        :has-name (dsl/organization-name
                   {:as (id "name")
                    :name legal-name})
        :has-identifier (dsl/organization-identifier
                         {:as (id "eia")
                          :scheme :urpx/eiaScheme
                          :skos/notation eia-id})})})))

(defn data-source
  "A DataSourceReference to pages `page-start` to `page-end` of `source`.
   `more` adds builder keys (leaves, a source publication, an `:as`)."
  ([source pages]
   (data-source source pages nil))
  ([{:keys [file url retrieved type]} [page-start page-end] more]
   (dsl/data-source-reference
    (merge {:file-name file
            :media-type :urpx/applicationPdf
            :access-url url
            :date-retrieved retrieved
            :data-source-type (or type :urpx/regulatoryWebsiteSource)
            :page-start page-start
            :page-end page-end}
           more))))

(defn coverage-claim
  "A CoverageClaim `cc` with result `result`, self-contained unless
   `:self-contained` is false, explained by `description` when given."
  [cc result {:keys [evaluated-on description self-contained]
              :or {self-contained true}}]
  (dsl/coverage-claim
   {:as cc
    :completeness-result result
    :self-contained self-contained
    :explained-by (when description
                    [(dsl/evaluation
                      {:as ((ider cc) "evaluation")
                       :evaluation-kind :urpx/coverageEvaluation
                       :description description
                       :evaluated-on (str evaluated-on "T00:00:00")})])}))

(defn metric-inputs [id prefix]
  [(dsl/metric-input
    {:as (id "mi-energy")
     :name "kWh Energy Consumption Prices"
     :metric-input-type :urpx/measuredMetricInput
     :has-metric-specification
     (dsl/metric-specification
      {:as (keyword prefix "ms-energy")
       :measurement-kind :urpx/energy
       :unit-of-measure :urpx/kWh})})
   (dsl/metric-input
    {:as (id "mi-meter-count")
     :name "Per Meter Prices"
     :metric-input-type :urpx/profileMetricInput
     :profile-metric-property :urpx/meterCount})])

(defn ledger [id name mi]
  (dsl/ledger
   {:as id
    :name name
    :ledger-type :urpx/bundledLedger
    :references-metric-input [mi]}))

(defn per-day [id]
  (dsl/calculation-method
   {:as id
    :interval-duration "P1D"}))

(defn xsd-time
  "\"17:00\" -> \"17:00:00\"; the end of the day, \"24:00\", is
   \"00:00:00\", since urpx.dsl refuses \"24:00:00\"."
  [hhmm]
  (str (if (= hhmm "24:00") "00:00" hhmm)
       ":00"))

(defn hundredths
  "16.10M (cents, or percent) to 0.1610M, scale kept."
  [c]
  (.movePointLeft ^BigDecimal c 2))

(defn version-dates
  "[[date next-date-or-nil] ...] from a date-keyed table."
  [table]
  (let [ds (sort (keys table))]
    (map vector
         ds
         (concat (rest ds) [nil]))))

(def ^:private node-schemas
  "The schemas of the nodes besides a package that a document's @graph
   holds. urpx.emit writes one root entity and has no writer for a
   SourcePublication or a RateCase, so these are encoded with its parts."
  {"urpx:ProgramEnrollment" schema/ProgramEnrollment
   "urpx:SourcePublication" schema/SourcePublication
   "urpx:RateCase" schema/RateCase})

(defn- emit-node
  "One top-level node as JSON data, with no @context."
  [node]
  (json/read-str
   (if (= "urpx:URPXPackage" (:jsonld/type node))
     (emit/write-urpx-package node {:context nil})
     (let [sch (or (node-schemas (:jsonld/type node))
                   (throw (ex-info (str "No schema to emit a " (:jsonld/type node))
                                   {:node (:jsonld/id node)})))]
       (json/write-str (core/keys->jsonld (coerce/encode sch node)))))))

(defn- key-order
  "@context, @id and @type first, then other keywords, then properties, each
   group in string order."
  [k]
  [(case k
     "@context" 0
     "@id" 1
     "@type" 2
     (if (str/starts-with? k "@") 3 4))
   k])

(defn- sort-keys
  "`x` with every map's keys in `key-order`, so the bytes written depend on
   the graph's content and not on the order its maps were built in."
  [x]
  (cond
    (map? x) (into (sorted-map-by #(compare (key-order %1) (key-order %2)))
                   (map (fn [[k v]]
                          [k (sort-keys v)]))
                   x)
    (sequential? x) (mapv sort-keys x)
    :else x))

(defn write!
  "Emit `doc` with @context `ctx` and write it to `path`, indented by two
   spaces, with every object's keys in `key-order` and slashes and non-ASCII
   characters unescaped. `doc` is one package, or a vector of top-level
   nodes written as an @graph."
  [doc ctx path]
  (let [data (sort-keys
              (if (sequential? doc)
                {"@context" ctx
                 "@graph" (mapv emit-node doc)}
                (json/read-str (emit/write-urpx-package doc {:context ctx}))))]
    (io/make-parents path)
    (spit path
          (str (json/write-str data
                               :indent true
                               :escape-slash false
                               :escape-unicode false)
               "\n"))
    path))

(defn fill
  "Replace each {key} in template `s` with (str (m :key))."
  [s m]
  (str/replace s
               #"\{([a-z0-9-]+)\}"
               (fn [[_ k]]
                 (let [v (get m (keyword k) ::missing)]
                   (when (= v ::missing)
                     (throw (ex-info (str "No value for {" k "}")
                                     {:template s})))
                   (str v)))))

(defn and-list
  "[\"a\" \"b\" \"c\"] -> \"a, b and c\"."
  [xs]
  (if (next xs)
    (str (str/join ", " (butlast xs))
         " and "
         (last xs))
    (first xs)))

(defn plain [^BigDecimal d]
  (.toPlainString d))

(def ^:private months
  ["January" "February" "March" "April" "May" "June" "July" "August"
   "September" "October" "November" "December"])

(defn long-date
  "\"2026-01-01\" -> \"January 1, 2026\"."
  [d]
  (let [[y m dd] (map parse-long (str/split d #"-"))]
    (str (months (dec m))
         " "
         dd
         ", "
         y)))
