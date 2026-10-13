;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.urpx
  "Generic URPX building blocks over urpx.dsl. Knows nothing about any
   utility."
  (:refer-clojure :exclude [ref])
  (:require [clojure.data.json :as json]
            [clojure.java.io :as io]
            [clojure.string :as str]
            [urpx.dsl :as dsl]
            [urpx.emit :as emit]))

(def urpx-version
  "https://github.com/urpx-org/urpx/raw/v0.5.1/ontology/urpx-ontology.ttl")

(def org-ns "https://rate-plans.grid-coordination.energy/organizations/")

(defn context [[p iri]]
  (merge emit/default-context
         {p iri
          "org" org-ns
          "skos" "http://www.w3.org/2004/02/skos/core#"}))

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

(defn customer-kind-rule
  "An EligibilityRule whose condition is hasCustomerKind = `kind`."
  [id {:keys [name description customer-kind]}]
  (let [rn (id "condition-expression-root-node")
        operand (ider rn)]
    (dsl/eligibility-rule
     {:as (id)
      :name name
      :description description
      :has-condition-expression
      (dsl/condition-expression
       {:as (id "condition-expression")
        :root-node
        (comparison rn
                    :urpx/equalsOperator
                    (dsl/object-operand-node
                     {:as (operand "left-operand")
                      :condition-property :urpx/hasCustomerKind})
                    (dsl/object-operand-node
                     {:as (operand "right-operand")
                      :references-value customer-kind}))})})))

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

(defn data-source [{:keys [file url retrieved]} [page-start page-end]]
  (dsl/data-source-reference
   {:file-name file
    :media-type :urpx/applicationPdf
    :access-url url
    :date-retrieved retrieved
    :data-source-type :urpx/regulatoryWebsiteSource
    :page-start page-start
    :page-end page-end}))

(defn coverage-claim [cc result {:keys [evaluated-on description]}]
  (dsl/coverage-claim
   {:as cc
    :completeness-result result
    :self-contained true
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

(defn write!
  "Emit `package` with @context `ctx` and write it to `path`, indented by two
   spaces, with slashes and non-ASCII characters unescaped."
  [package ctx path]
  (let [s (emit/write-urpx-package package {:context ctx})]
    (io/make-parents path)
    (spit path
          (str (json/write-str (json/read-str s)
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
