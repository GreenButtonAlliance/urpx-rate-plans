;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.alternatives
  "Expand a rate plan modifier whose customer chooses one alternative along a
   single string dimension (e.g. a jurisdiction). Each alternative carries
   percentage multipliers over prices of the base plan's version, and may
   carry per-kWh charges. Knows nothing about any utility."
  (:require [rate-plans.urpx :as u]
            [urpx.dsl :as dsl]))

(defn- alternative [id {:keys [property]} [k n]]
  (let [cn (id "cn-pa" k)
        operand (u/ider cn)]
    (dsl/profile-alternative
     {:as (id "pa" k)
      :name (str "Service location in " n)
      :has-condition-expression
      (dsl/condition-expression
       {:as (id "cx-pa" k)
        :root-node
        (u/comparison cn
                      :urpx/equalsOperator
                      (dsl/custom-operand-node
                       {:as (operand "left-operand")
                        :custom-condition-property property})
                      (dsl/custom-operand-node
                       {:as (operand "right-operand")
                        :string-value n}))})})))

(defn- profile-alternatives [id {:keys [dimension alternatives]}]
  (let [pa (id "pa" (:slug dimension))]
    (dsl/profile-alternatives
     {:as pa
      :name (:name dimension)
      :has-alternative-dimensions
      (dsl/alternative-dimensions
       {:as ((u/ider pa) "alternative-dimensions")
        :has-alternative-dimension
        [(dsl/alternative-dimension
          {:as (id "ad" (:slug dimension))
           :dimension-display-name (:display-name dimension)
           :custom-dimension-property (:property dimension)
           :has-possible-values
           (dsl/rdf-list (for [[_ n] alternatives]
                           {:jsonld/value n
                            :jsonld/type "xsd:string"}))})]})
      :has-profile-alternative (mapv #(alternative id dimension %)
                                     alternatives)})))

(defn package
  "One RatePlanModifier with one RatePlanModifierVersion. See
   rate-plans.us.wa.scl.residential-suburban for the keys."
  [{:keys [utility schedule version next source pages base base-ids alternatives
           percentages per-kwh per-kwh-since multipliers dimension names] :as plan}]
  (dsl/dsl-scope
   (let [[p] (:prefix utility)
         id (u/ider (keyword p (str schedule "-" version)))
         per-kwh-rows (for [[j rows] per-kwh
                            [s label c] rows]
                        [j s label c])
         alt-name (into {} alternatives)
         pk (:per-kwh-slug names)

         ledgers
         (conj (mapv (fn [{:keys [slug ledger-name metric]}]
                       (u/ledger (id "ledger" slug)
                                 ledger-name
                                 (id metric)))
                     multipliers)
               (u/ledger (id "ledger" pk)
                         (:per-kwh-ledger names)
                         (id "mi-energy")))

         multiplier-definition
         (fn [{:keys [slug pd-name per-day?]}]
           (dsl/price-definition
            {:as (id "pd" slug)
             :name pd-name
             :charge-type :urpx/taxMunicipal
             :charge-category :urpx/taxes
             :bill-portion :urpx/bundledPortion
             :base-quantity (when per-day? 1)
             :has-calculation-method
             (when per-day?
               (u/per-day (id "pd" slug "calculation-method")))
             :references-ledger (id "ledger" slug)}))

         per-kwh-definition
         (fn [[j s label]]
           (dsl/price-definition
            {:as (id "pd" pk s)
             :name (str label
                        (:per-kwh-suffix names)
                        " ("
                        (alt-name j)
                        ")")
             :charge-type :urpx/recoverySurcharge
             :charge-category :urpx/adjustment
             :bill-portion :urpx/bundledPortion
             :references-ledger (id "ledger" pk)}))

         billing-model
         (dsl/billing-model
          {:as (id "plan-elements-billing-model")
           :has-ledger ledgers
           :has-price-definition
           (into (mapv multiplier-definition multipliers)
                 (map per-kwh-definition)
                 per-kwh-rows)})

         plan-elements
         (dsl/plan-elements
          {:as (id "plan-elements")
           :has-metric-input (u/metric-inputs id p)
           :has-profile-alternatives (profile-alternatives id plan)
           :has-billing-model billing-model})

         multiplier-price
         (fn [j n pct {:keys [slug based-on of-what]}]
           (dsl/price
            {:as (id "price" j slug)
             :references-price-definition (id "pd" slug)
             :start-date version
             :name (str n
                        " "
                        (:multiplier names)
                        ", "
                        (.toPlainString ^BigDecimal pct)
                        " percent of "
                        of-what)
             :multiplier (u/hundredths pct)
             :based-on-price [(u/ref (base-ids based-on))]}))

         per-kwh-price
         (fn [[s label c]]
           (dsl/price
            {:as (id "price" pk s)
             :references-price-definition (id "pd" pk s)
             :start-date per-kwh-since
             :name (str label (:per-kwh-suffix names))
             :unit-price (u/hundredths c)}))

         price-set-alternative
         (fn [[j n]]
           (let [pct (percentages j)]
             (dsl/price-set-alternative
              {:as (id "psa" j)
               :references-profile-alternative (id "pa" j)
               :has-price
               (into (mapv #(multiplier-price j n pct %)
                           multipliers)
                     (map per-kwh-price)
                     (per-kwh j))})))

         prices
         (dsl/prices
          {:as (id "prices")
           :has-price-set-alternatives
           [(dsl/price-set-alternatives
             {:as (id "psa-by" (:slug dimension))
              :name (:psa names)
              :references-profile-alternatives
              (id "pa" (:slug dimension))
              :has-price-set-alternative
              (mapv price-set-alternative alternatives)})]})

         modifier-version
         (dsl/rate-plan-modifier-version
          {:as (id)
           :version version
           :modifier-version-number version
           :change-reason :urpx/rateCase
           :description (:description plan)
           :effective-date-time (str version "T00:00:00")
           :expiration-date-time (some-> next
                                         (str "T00:00:00"))
           :price-currency "USD"
           :commodity [:urpx/electricity]
           :service-role :urpx/bundledServiceRole
           :applicable-to-rate-plan [(u/ref (str p ":" base))]
           :has-data-source-reference [(u/data-source source pages)]
           :has-eligibility-rule
           [(u/customer-kind-rule (u/ider (id "er-residential"))
                                  (:eligibility plan))]
           :has-plan-elements plan-elements
           :has-prices prices
           :offered-by (u/utility-operator utility)
           :for-rate-plan-modifier (keyword p schedule)
           :has-coverage-claim
           (u/coverage-claim (keyword p (str "cc-" schedule "-" version))
                             (get-in plan [:coverage :result])
                             nil)})]
     (dsl/urpx-package
      {:as (keyword p (str "doc-" schedule "-" version))
       :target-urpx-version u/urpx-version
       :has-rate-plan-modifier
       [(dsl/rate-plan-modifier
         {:as (keyword p schedule)
          :name (:name plan)
          :modifier-unique-identifier (:identifier plan)
          :initial-effective-date (:initial-effective-date plan)
          :timezone-identifier (:timezone utility)
          :has-rate-plan-modifier-version modifier-version})]}))))
