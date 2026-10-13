;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.us.ca.pge.e-tou-c-medical-baseline
  "PG&E Electric Rule 19's Standard Medical Baseline Quantity added to
   Schedule E-TOU-C's baseline ladder, and the Medical Baseline Wildfire Fund
   Charge exemption. One version per E-TOU-C version, in that version's
   filing directory, naming its tiers and Price through
   rate-plans.us.ca.pge.e-tou-c."
  (:require [rate-plans.defs :refer [as-of]]
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

(defurpx :rate-plans.kind/description prose
  {:version
   (str "PG&E Electric Rule 19, Part A: \"The Standard Medical Baseline Quantity is {quantity} kWh per day (approximately) year-round.\" "
        "Schedule E-TOU-C Special Condition 5 (Sheet 6, Cal. P.U.C. Sheet 61129-E): \"Standard medical quantities are added to the baseline usage from Special Condition 1 to increase the maximum level of usage subject to baseline (Tier 1) rates.\" "
        "Its heading names the two results: Code M, Basic Plus Medical Quantities, is Code B plus the medical quantity, and Code S, All-Electric Plus Medical Quantities, is Code H plus it. "
        "This version adds {quantity} kWh per day to the Tier 1 upper bound and the Tier 2 lower bound of {base}, and {multiple} kWh per day, four times {quantity}, to the Tier 2 upper bound and the Tier 2 Continued lower bound, because Tier 2 ends at four times the baseline quantity and the medical quantity is part of the baseline. "
        "The base version's ladder ends Tier 2 at four times the Special Condition 1 quantity, the Tier 2 that Schedule E-1 prints as \"Tier 2 Usage (101% - 400% of Baseline)\"; no E-TOU-C sheet states the 400 percent figure, which the base version's manifest records as a deferral. "
        "The quantity is the same in every baseline territory, code and season, so each of the {brackets} urpx:ServiceBracket here names one base tier with urpx:adjustsServiceTier and no territory, code or season, one for each of the four bounds, because the base tiers carry season on their own brackets; the Code B or Code H cell selected on the base decides which bound moves. "
        "Rule 19 Part A also states that \"The Standard Medical Baseline Quantity used for automated billing is calculated using the unrounded quotient of the following equation: 6,000 kWh per year divided by 365 days. Any billing that requires hand calculations will use {quantity} kWh per day.\" "
        "The quotient (16.438356...) has no terminating decimal form, so this version carries {quantity}, the figure Rule 19 prints. "
        "Customers receiving a medical baseline allowance do not pay the Wildfire Fund Charge (Sheet 1, Cal. P.U.C. Sheet 61124-E, and Special Condition 11, Sheet 10, Cal. P.U.C. Sheet 61133-E: the charge \"applies to all retail sales, excluding CARE and Medical Baseline sales\"), so this version also carries an exemption Price at urpx:multiplier -1 over {wildfire-fund}, the shape pge:d-care uses. "
        "urpx:adjustsServiceTier, urpx:lowerBoundOffset and urpx:upperBoundOffset are proposed in urpx-org/urpx#80 and are in no URPX release.")
   :eligibility "Rule 19 Part B: \"To qualify for a Standard Medical Baseline Quantity, you must certify in writing that you or a full-time resident in your home is\" dependent on a life-support device used in the home, a paraplegic, hemiplegic or quadriplegic person or a multiple sclerosis patient with special heating or cooling needs, a person being treated for a life-threatening illness or with a compromised immune system with special heating or cooling needs, or a scleroderma patient with special heating needs, with other conditions reviewed individually. Part C sets recertification every four years for a permanent condition and every two years otherwise. Carried as one enrollment condition, as sce:medical-baseline carries it."
   :coverage "Rule 19 Part F's Additional Medical Baseline Quantities, which PG&E assigns case by case in increments of {quantity} kWh per day, are not carried: this version adds one Standard Medical Baseline Quantity. The offsets are kWh per day, as are the bounds they adjust, and this document does not state how a consumer scales either to a billing period. The adjusting brackets name the tier @ids of {base}, so a later version of the schedule needs its own version of this modifier. A customer on both CARE and Medical Baseline is exempt from the Wildfire Fund Charge once, but pge:d-care and this modifier each carry a -1 multiple of the same Price, so a composition holding both would credit it twice; the one-modifier composition policy in this repository never builds that composition."})

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
   (let [id (u/ider (keyword "pge" (str "e-tou-c-medical-baseline-" date)))
         q (:quantity (as-of pge/medical-quantity date))
         offsets {:quantity q
                  :multiple (e-tou-c/over-baseline-multiple q)}
         wildfire-fund (e-tou-c/price-iri date "wildfire-fund")
         words {:quantity (u/plain q)
                :multiple (u/plain (:multiple offsets))
                :base (dsl/curie (e-tou-c/version-id date))
                :brackets (count adjustments)
                :wildfire-fund wildfire-fund}]
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
            :description (u/fill (:version prose) words)
            :effective-date-time (str date "T00:00:00")
            :expiration-date-time (some-> next (str "T00:00:00"))
            :price-currency "USD"
            :commodity [:urpx/electricity]
            :service-role :urpx/bundledServiceRole
            :applicable-to-rate-plan [(u/ref "pge:e-tou-c")]
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
               :description (:eligibility prose)
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
                                      :adjusts-service-tier (u/ref (e-tou-c/tier-iri date rung))}
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
                 :name (str "Medical Baseline Wildfire Fund Charge exemption: the negative of " wildfire-fund)
                 :references-price-definition (id "pd-wildfire-fund-exemption")
                 :multiplier -1M
                 :based-on-price [(u/ref wildfire-fund)]
                 :start-date date})]})
            :offered-by (u/utility-operator pge/pge)
            :for-rate-plan-modifier :pge/e-tou-c-medical-baseline
            :has-coverage-claim
            (u/coverage-claim (keyword "pge" (str "cc-e-tou-c-medical-baseline-" date))
                              :urpx/partial
                              {:self-contained false
                               :evaluated-on "2026-10-07"
                               :description (u/fill (:coverage prose) words)})})})]}))))

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
