;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.us.ca.pge.e-tou-c-medical-baseline
  "PG&E Electric Rule 19's Standard Medical Baseline Quantity added to
   Schedule E-TOU-C's baseline ladder, and the Medical Baseline Wildfire Fund
   Charge exemption. One version per E-TOU-C version, in that version's
   filing directory, naming its tiers and Price through
   rate-plans.us.ca.pge.e-tou-c. Its prose is in
   prose/e-tou-c-medical-baseline/."
  (:require [rate-plans.defs :refer [as-of]]
            [rate-plans.prose :as md]
            [rate-plans.urpx :as u]
            [rate-plans.us.ca.pge.common :as pge]
            [rate-plans.us.ca.pge.e-tou-c :as e-tou-c]
            [urpx.defs :refer [defurpx]]
            [urpx.dsl :as dsl]))

(def rule-19
  "Electric Rule 19, Medical Baseline Quantities."
  {:file "ELEC_RULES_19.pdf"
   :url "https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_RULES_19.pdf"
   :retrieved "2026-10-07"
   :type :urpx/utilityWebsiteSource})

(def ^:private adjustments
  "Each base tier bound the quantity moves, and by how many quantities: the
   Tier 1 ceiling and Tier 2 floor by one, the Tier 2 ceiling and Tier 2
   Continued floor by the over-baseline multiple."
  ;; rung   bound    offset
  [["t1"   :upper   :quantity]
   ["t2"   :lower   :quantity]
   ["t2"   :upper   :multiple]
   ["t2c"  :lower   :multiple]])

(defn package
  "Version `date` of the modifier, over version `date` of E-TOU-C."
  [doc date next]
  (dsl/dsl-scope
   {:outside (into {:pge/e-tou-c "urpx:RatePlan"
                    (e-tou-c/price-id date "wildfire-fund") "urpx:Price"}
                   (for [[rung] adjustments]
                     [(e-tou-c/tier-id date rung) "urpx:ServiceTier"]))}
   (let [id (u/ider (keyword "pge" (str "e-tou-c-medical-baseline-" date)))
         q (:quantity (as-of pge/medical-quantity date))
         offsets {:quantity q
                  :multiple (e-tou-c/over-baseline-multiple q)}
         wildfire-fund (e-tou-c/price-id date "wildfire-fund")
         words {:quantity (u/plain q)
                :multiple (u/plain (:multiple offsets))
                :base (dsl/curie (e-tou-c/version-id date))
                :brackets (count adjustments)
                :wildfire-fund (dsl/curie wildfire-fund)}]
     (dsl/urpx-package
      {:as (keyword "pge" (str "doc-e-tou-c-medical-baseline-" date))
       :target-urpx-version u/urpx-version
       :has-rate-plan-modifier
       [(dsl/rate-plan-modifier
         {:as :pge/e-tou-c-medical-baseline
          :name (:name doc)
          :modifier-unique-identifier (:identifier doc)
          :initial-effective-date (:initial-effective-date doc)
          :timezone-identifier (:timezone pge/pge)
          :has-rate-plan-modifier-version
          (dsl/rate-plan-modifier-version
           {:as (id)
            :version date
            :modifier-version-number date
            :change-reason :urpx/rateCase
            :description (u/fill (md/text ::version) words)
            :effective-date-time (u/xsd-date-time date)
            :expiration-date-time (some-> next u/xsd-date-time)
            :price-currency "USD"
            :commodity [:urpx/electricity]
            :service-role :urpx/bundledServiceRole
            :applicable-to-rate-plan [:pge/e-tou-c]
            :has-data-source-reference
            [(u/data-source rule-19
                            [1 3]
                            {:as (id "data-source-reference")
                             :leaf-start "55539-E"
                             :leaf-end "55541-E"})]
            :has-eligibility-rule
            [(dsl/eligibility-rule
              {:as (id "er-eligible")
               :name "Customer certified for Medical Baseline under Electric Rule 19"
               :description (md/text ::eligibility)
               :has-condition-expression
               (dsl/condition-expression
                {:as (id "cx-eligible")
                 :root-node (u/custom-comparison (id "cx-eligible-root-node")
                                                 "Program Enrollment"
                                                 :string-value
                                                 "Medical Baseline")})})]
            :has-plan-elements
            (dsl/plan-elements
             {:as (id "plan-elements")
              :has-metric-input
              [(dsl/metric-input
                {:as (id "mi-energy")
                 :name "kWh Energy Consumption"
                 :metric-input-type :urpx/measuredMetricInput
                 :has-metric-specification
                 (dsl/metric-specification
                  {:as (id "ms-energy")
                   :measurement-kind :urpx/energy
                   :unit-of-measure :urpx/kWh})})]
              :has-billing-model
              (dsl/billing-model
               {:as (id "plan-elements-billing-model")
                :has-service-tiers
                [(dsl/service-tiers
                  {:as (id "tiers-medical")
                   :references-metric-input [(id "mi-energy")]
                   :has-service-tier
                   [(dsl/service-tier
                     {:as (id "tier-medical-host")
                      :name "Standard Medical Baseline Quantity, added to the E-TOU-C baseline ladder"
                      :has-service-bracket
                      (vec (for [[rung bound offset] adjustments]
                             (dsl/service-bracket
                              (merge {:as (id "bracket-tier-baseline" rung (name bound))
                                      :adjusts-service-tier (e-tou-c/tier-id date rung)}
                                     (case bound
                                       :lower {:lower-bound-offset (offsets offset)}
                                       :upper {:upper-bound-offset (offsets offset)})))))})]})]
                :has-ledger
                [(u/ledger (id "ledger-wildfire-fund-exemption")
                           "Medical Baseline Wildfire Fund Charge exemption"
                           (id "mi-energy"))]
                :has-price-definition
                [(dsl/price-definition
                  {:as (id "pd-wildfire-fund-exemption")
                   :name "Medical Baseline Wildfire Fund Charge exemption"
                   :charge-type :urpx/creditEnergy
                   :charge-category :urpx/discount
                   :bill-portion :urpx/bundledPortion
                   :references-ledger (id "ledger-wildfire-fund-exemption")})]})})
            :has-prices
            (dsl/prices
             {:as (id "prices")
              :has-price
              [(dsl/price
                {:as (id "price-wildfire-fund-exemption")
                 :name (str "Medical Baseline Wildfire Fund Charge exemption: the negative of " (dsl/curie wildfire-fund))
                 :references-price-definition (id "pd-wildfire-fund-exemption")
                 :multiplier -1M
                 :based-on-price [wildfire-fund]
                 :start-date date})]})
            :offered-by (u/utility-operator pge/pge)
            :for-rate-plan-modifier :pge/e-tou-c-medical-baseline
            :has-coverage-claim
            (u/coverage-claim (keyword "pge" (str "cc-e-tou-c-medical-baseline-" date))
                              :urpx/partial
                              {:self-contained false
                               :evaluated-on "2026-10-07"
                               :description (u/fill (md/text ::coverage) words)})})})]}))))

(defurpx :rate-plans.kind/document e-tou-c-medical-baseline
  {:kind :rate-plan-modifier
   :utility pge/pge
   :schedule "e-tou-c-medical-baseline"
   :filing "e-tou-c"
   :identifier "E-TOU-C-MEDICAL-BASELINE"
   :name "Schedule E-TOU-C Standard Medical Baseline Quantity (Electric Rule 19)"
   :initial-effective-date "2023-03-23"
   :versions e-tou-c/filings
   :expand package})
