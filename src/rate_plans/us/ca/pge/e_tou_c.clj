;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.us.ca.pge.e-tou-c
  "PG&E Schedule E-TOU-C, Residential Time-Of-Use (Peak Pricing 4-9 p.m.
   Every Day), and its Vintaged PCIA modifier, which each base version's
   document carries. Every table is keyed by the date it takes effect; a
   later filing adds a key."
  (:require [clojure.string :as str]
            [rate-plans.defs :refer [as-of effective-key]]
            [rate-plans.prose :as md]
            [rate-plans.tou :as tou]
            [rate-plans.urpx :as u]
            [rate-plans.us.ca.pge.common :as pge]
            [rate-plans.words :as words]
            [urpx.defs :refer [defurpx]]
            [urpx.dsl :as dsl]))

;; ---------------------------------------------------------------------------
;; Filings
;; ---------------------------------------------------------------------------

(def tariff
  "The schedule's tariff document; every filing reissues it at this URL."
  {:file "ELEC_SCHEDS_E-TOU-C.pdf"
   :url "https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_E-TOU-C.pdf"
   :type :urpx/utilityWebsiteSource})

(defurpx :rate-plans.kind/filings filings
  "One entry per version: the tariff document as retrieved, the Cal. P.U.C.
   sheets it spans, and the advice letter and decision that issued it."
  {"2026-03-01" {:retrieved "2026-04-26"
                 :leaves ["61124-E" "61133-E"]
                 :advice-letter "7846-E"
                 :change-reason :urpx/rateCase
                 :evaluated-on "2026-09-21"}
   "2026-03-27" {:retrieved "2026-04-28"
                 :leaves ["61124-E" "61249-E"]
                 :advice-letter "7869-E"
                 :decision "D.26-03-013"
                 :change-reason :urpx/rateCase
                 :evaluated-on "2026-09-22"}
   "2026-06-01" {:retrieved "2026-09-23"
                 :leaves ["61124-E" "61364-E"]
                 :advice-letter "7921-E"
                 :decision "D.26-04-036"
                 :change-reason :urpx/regulatoryOrder
                 :evaluated-on "2026-10-07"}})

;; ---------------------------------------------------------------------------
;; Seasons and time-of-use periods
;; ---------------------------------------------------------------------------

(defurpx :rate-plans.kind/seasons seasons
  "Sheet 2: Summer June 1 through September 30, Winter October 1 through May
   31."
  {"2026-03-01"
   ;; key      name      months
   [[:summer  "Summer"  [6 7 8 9]]
    [:winter  "Winter"  [10 11 12 1 2 3 4 5]]]})

(defurpx :rate-plans.kind/tou-tiers tou-tiers
  "Sheet 1, TIME PERIODS: peak 4 p.m. to 9 p.m. every day, off-peak all other
   hours, in both seasons. Row order gives the tier numbers; season-major
   order within a tier gives the period numbers."
  {"2026-03-01"
   ;; key        label       standard name         brackets: slug start end
   [[:peak      "Peak"      :urpx/peakTier       [[nil   "16:00" "21:00"]]]
    [:off-peak  "Off-Peak"  :urpx/offPeakTier    [["am"  "00:00" "16:00"]
                                                  ["pm"  "21:00" "24:00"]]]]})

;; ---------------------------------------------------------------------------
;; Charges and rates
;; ---------------------------------------------------------------------------

(defurpx :rate-plans.kind/ledgers ledgers
  ;; key               name                                 type                  metric input
  [[:energy-supply    "Energy Supply Prices"               :urpx/supplyLedger    :mi-energy]
   [:energy-delivery  "Energy Delivery Prices"             :urpx/deliveryLedger  :mi-energy]
   [:adjustments      "Adjustment Prices"                  :urpx/bundledLedger   :mi-energy]
   [:cia              "Conservation Incentive Adjustment"  :urpx/bundledLedger   :mi-energy-baseline]
   [:base-charge      "Base Services Charge"               :urpx/bundledLedger   :mi-meter-count]
   [:climate-credit   "California Climate Credit"          :urpx/bundledLedger   :mi-household-count]])

(defurpx :rate-plans.kind/charges charges
  "Sheet 3, Unbundling of Total Rates, $ per kWh, in PriceDefinition order.
   A row with a period is priced in that time-of-use period."
  ;; key                    name                                            charge type                 category                 portion                ledger            price set      period
  [[:gen-summer-peak       "Generation Summer Peak"                        :urpx/usageCharge           :urpx/auxiliaryCharge    :urpx/supplyPortion    :energy-supply    :generation    :summer-peak]
   [:gen-summer-off-peak   "Generation Summer Off-Peak"                    :urpx/usageCharge           :urpx/auxiliaryCharge    :urpx/supplyPortion    :energy-supply    :generation    :summer-off-peak]
   [:gen-winter-peak       "Generation Winter Peak"                        :urpx/usageCharge           :urpx/auxiliaryCharge    :urpx/supplyPortion    :energy-supply    :generation    :winter-peak]
   [:gen-winter-off-peak   "Generation Winter Off-Peak"                    :urpx/usageCharge           :urpx/auxiliaryCharge    :urpx/supplyPortion    :energy-supply    :generation    :winter-off-peak]
   [:bundled-pcia          "Bundled Power Charge Indifference Adjustment"  :urpx/adjustmentPowerCost   :urpx/adjustment         :urpx/supplyPortion    :energy-supply    :generation    nil]
   [:dist-summer-peak      "Distribution Summer Peak"                      :urpx/usageCharge           :urpx/auxiliaryCharge    :urpx/deliveryPortion  :energy-delivery  :distribution  :summer-peak]
   [:dist-summer-off-peak  "Distribution Summer Off-Peak"                  :urpx/usageCharge           :urpx/auxiliaryCharge    :urpx/deliveryPortion  :energy-delivery  :distribution  :summer-off-peak]
   [:dist-winter-peak      "Distribution Winter Peak"                      :urpx/usageCharge           :urpx/auxiliaryCharge    :urpx/deliveryPortion  :energy-delivery  :distribution  :winter-peak]
   [:dist-winter-off-peak  "Distribution Winter Off-Peak"                  :urpx/usageCharge           :urpx/auxiliaryCharge    :urpx/deliveryPortion  :energy-delivery  :distribution  :winter-off-peak]
   [:cia                   "Conservation Incentive Adjustment"             :urpx/conservationCharge    :urpx/adjustment         :urpx/bundledPortion   :cia              :cia           nil]
   [:transmission          "Transmission"                                  :urpx/transmission          :urpx/adjustment         :urpx/deliveryPortion  :energy-delivery  :distribution  nil]
   [:transmission-adj      "Transmission Rate Adjustments"                 :urpx/transmission          :urpx/adjustment         :urpx/deliveryPortion  :energy-delivery  :distribution  nil]
   [:reliability           "Reliability Services"                          :urpx/reliabilityCharge     :urpx/adjustment         :urpx/deliveryPortion  :energy-delivery  :distribution  nil]
   [:public-purpose        "Public Purpose Programs"                       :urpx/publicBenefits        :urpx/regulatory         :urpx/bundledPortion   :adjustments      :adjustment    nil]
   [:nuclear               "Nuclear Decommissioning"                       :urpx/environmentalFunding  :urpx/environmental      :urpx/bundledPortion   :adjustments      :adjustment    nil]
   [:ctc                   "Competition Transition Charges"                :urpx/transitionCharge      :urpx/adjustment         :urpx/bundledPortion   :adjustments      :adjustment    nil]
   [:energy-cost-recovery  "Energy Cost Recovery Amount"                   :urpx/recoverySurcharge     :urpx/adjustment         :urpx/bundledPortion   :adjustments      :adjustment    nil]
   [:wildfire-fund         "Wildfire Fund Charge"                          :urpx/environmentalFunding  :urpx/environmental      :urpx/bundledPortion   :adjustments      :adjustment    nil]
   [:wildfire-hardening    "Wildfire Hardening Charge"                     :urpx/environmentalFunding  :urpx/environmental      :urpx/bundledPortion   :adjustments      :adjustment    nil]
   [:recovery-bond         "Recovery Bond Charge"                          :urpx/recoverySurcharge     :urpx/adjustment         :urpx/bundledPortion   :adjustments      :adjustment    nil]
   [:recovery-bond-credit  "Recovery Bond Credit"                          :urpx/creditMisc            :urpx/adjustment         :urpx/bundledPortion   :adjustments      :adjustment    nil]])

(defurpx :rate-plans.kind/dollars rates
  "Sheet 3, $ per kWh. The Conservation Incentive Adjustment has one rate per
   baseline tier."
  {"2026-03-01" {:gen-summer-peak 0.20782M :gen-summer-off-peak 0.10482M
                 :gen-winter-peak 0.13710M :gen-winter-off-peak 0.11042M
                 :bundled-pcia -0.01011M
                 :dist-summer-peak 0.20388M :dist-summer-off-peak 0.18388M
                 :dist-winter-peak 0.14977M :dist-winter-off-peak 0.14645M
                 :cia-t1 -0.02786M :cia-t2 0.05354M :cia-t2c 0.05354M
                 :transmission 0.04638M :transmission-adj 0.00453M :reliability 0.00013M
                 :public-purpose 0.00614M :nuclear -0.00002M :ctc 0.00027M
                 :energy-cost-recovery 0.00002M :wildfire-fund 0.00591M
                 :wildfire-hardening 0.00391M :recovery-bond 0.00857M
                 :recovery-bond-credit -0.00857M}})

(defurpx :rate-plans.kind/dollars base-services-charge
  "Sheet 2, Base Services Charge, $ per meter per day, by income tier."
  {"2026-03-01" {:care 0.19713M :fera 0.39688M :standard 0.79343M}})

(defurpx :rate-plans.kind/climate-credit climate-credit
  "Sheet 2, California Climate Credit, $ per household, in the bill months
   given. AL 7869-E removed it; AL 7921-E restored it as a semi-annual payment
   in August and September."
  {"2026-03-01" {:amount -36.18M :months [4 10]}
   "2026-03-27" {}
   "2026-06-01" {:amount -36.18M :months [8 9]}})

(defurpx :rate-plans.kind/dollars vintage-pcia-rates
  "Sheet 8, Vintaged Power Charge Indifference Adjustment, $ per kWh, by
   departure vintage year."
  {"2026-03-01" {2009 0.02973M 2010 0.03366M 2011 0.03492M 2012 0.03676M
                 2013 0.03708M 2014 0.03686M 2015 0.03680M 2016 0.03687M
                 2017 0.03661M 2018 0.03679M 2019 0.03725M 2020 0.03632M
                 2021 0.05264M 2022 0.05272M 2023 0.05380M 2024 0.05066M
                 2025 -0.01011M 2026 -0.01011M}})

;; ---------------------------------------------------------------------------
;; Income tiers and baseline quantities
;; ---------------------------------------------------------------------------

(defurpx :rate-plans.kind/income-tiers income-tiers
  "Sheet 1, RATES: the income tier sets the Base Services Charge."
  ;; key        label                                     enrolled in  enrolled in neither
  [[:care      "Income Tier 1 (CARE-eligible)"           [:care]      []]
   [:fera      "Income Tier 2 (FERA-eligible)"           [:fera]      []]
   [:standard  "Income Tier 3 (neither CARE nor FERA)"   []           [:care :fera]]])

(defurpx :rate-plans.kind/baseline-quantities baseline-quantities
  "Special Condition 1, Sheet 5 (Cal. P.U.C. Sheet 61128-E), Baseline
   Quantities in kWh per day, identical in every version's PDF."
  {"2026-03-01"
   ;; territory  Code B summer  Code B winter  Code H summer  Code H winter
   [["P"         13.5M          11.0M          15.2M          26.0M]
    ["Q"         9.8M           11.0M          8.5M           26.0M]
    ["R"         17.7M          10.4M          19.9M          26.7M]
    ["S"         15.0M          10.2M          17.8M          23.7M]
    ["T"         6.5M           7.5M           7.1M           12.9M]
    ["V"         7.1M           8.1M           10.4M          19.1M]
    ["W"         19.2M          9.8M           22.4M          19.0M]
    ["X"         9.8M           9.7M           8.5M           14.6M]
    ["Y"         10.5M          11.1M          12.0M          24.0M]
    ["Z"         5.9M           7.8M           6.7M           15.7M]]})

(def codes
  "Special Condition 1's baseline codes, in the column order of
   `baseline-quantities`."
  ["B" "H"])

(defn over-baseline-multiple
  "Tier 2 ends at this multiple of the baseline quantity (see the deferral
   on the 4x figure)."
  [q]
  (* 4M q))

;; ---------------------------------------------------------------------------
;; IRIs another document names
;; ---------------------------------------------------------------------------

(defn version-id
  "The keyword naming version `date` of the plan, :pge/e-tou-c-<date>."
  [date]
  (keyword "pge" (str "e-tou-c-" date)))

(defn tier-id
  "The keyword naming baseline tier `rung` (t1, t2, t2c) of version `date`."
  [date rung]
  ((u/ider (version-id date)) "tier-baseline" rung))

(defn price-id
  "The keyword naming the Price of charge `k` in version `date`."
  [date k]
  ((u/ider (version-id date)) "price" k))

;; ---------------------------------------------------------------------------
;; Prose
;; ---------------------------------------------------------------------------

(defurpx :rate-plans.kind/description prose
  "Short prose. Longer prose is in prose/e-tou-c/, loaded by key through
   rate-plans.prose."
  {:vintage-pcia "Vintage PCIA for CCA/DA/TBS customers is modeled as a sibling RatePlanModifier in this file."
   :medical-baseline "The Standard Medical Baseline Quantity of Electric Rule 19 (Code M and Code S) is the modifier pge:e-tou-c-medical-baseline, a second document in this filing's directory."
   :ladder-names
   "Income tier (CARE / FERA / standard) by Baseline Territory and Baseline Code (Sheet 1 RATES; Special Condition 1, Sheet 5)"
   :bsc-alternatives
   "Base Services Charge by income tier (CARE / FERA / standard), one alternative per income tier, Baseline Territory and Baseline Code cell"})

(defurpx :rate-plans.kind/description tier-names
  {:t1 "Tier 1, baseline usage: kWh per day up to the Special Condition 1 quantity"
   :t2 "Tier 2, over baseline usage: kWh per day above the Special Condition 1 quantity, to four times it"
   :t2c "Tier 2 Continued: kWh per day above four times the Special Condition 1 quantity"
   :cia-t1 "Tier 1 (baseline usage)"
   :cia-t2 "Tier 2 (over baseline usage)"
   :cia-t2c "Tier 2 Continued (over baseline usage)"})

(defurpx :rate-plans.kind/discountable discountable
  "The subtotals Schedules D-CARE and E-FERA discount: every volumetric
   charge but those excluded, the Conservation Incentive Adjustment counted
   once across its baseline tiers."
  {"2026-03-01" {}
   "2026-03-27"
   {:care {:excludes [:wildfire-fund :wildfire-hardening :recovery-bond :recovery-bond-credit]
           :name ::discountable-care}
    :fera {:excludes [:wildfire-hardening :recovery-bond :recovery-bond-credit]
           :name ::discountable-fera}}})

(defurpx :rate-plans.kind/coverage coverage
  "Each version's coverage evaluation: a prose file, or, from 2026-03-27, the
   filing's tariff.toml [modeling].deferrals, which must cite each figure
   under :cites as the rate tables give it."
  {"2026-03-01" {:text ::coverage-2026-03-01}
   "2026-03-27" {:deferrals {:cites [:version
                                     :medical-baseline
                                     :bsc-slash
                                     :standard-bsc
                                     :fera-bsc
                                     :medical-quantity
                                     :p-summer
                                     :p-summer-30
                                     :cia-t2]}}})

(defurpx :rate-plans.kind/description vintage-pcia-prose
  {:residential "Vintaged PCIA applies only to residential customers."
   :da-tbs "Vintaged PCIA under this modifier applies to customers taking Direct Access service or Transitional Bundled Service. Community Choice Aggregation customers take it from pge:cca-crs."})

;; ---------------------------------------------------------------------------
;; Expansion
;; ---------------------------------------------------------------------------

(defn- periods
  "[[period-key tier-key season-key label number] ...] in tier-major order,
   numbered from 1."
  [tiers seasons]
  (map-indexed (fn [i [p t s label]]
                 [p t s label (inc i)])
               (for [[t label] tiers
                     [s season-name] seasons]
                 [(keyword (str (name s) "-" (name t)))
                  t
                  s
                  (str season-name " " label)])))

(defn- tou-schedule [id tiers seasons]
  (let [ps (periods tiers seasons)]
    (dsl/tou-schedule
     {:as (id "c")
      :references-metric-input [(id "mi-energy")]
      :has-tou-tier
      (vec (map-indexed
            (fn [i [t label standard brackets]]
              (dsl/tou-tier
               {:as (id "tier" t)
                :tier-source-name label
                :tou-tier-standard-name standard
                :tou-tier-number (inc i)
                :has-tou-period
                (vec (for [[p pt s plabel n] ps
                           :when (= pt t)]
                       (dsl/tou-period
                        {:as (id "period" p)
                         :name (str plabel " Period")
                         :tou-period-number n
                         :has-time-bracket
                         (vec (for [[slug start end] brackets]
                                (dsl/time-bracket
                                 {:as (apply id "time-bracket" p (when slug [slug]))
                                  :start-time (u/xsd-time start)
                                  :end-time (u/xsd-time end)
                                  :applies-in-season (id "season" s)
                                  :day-type :urpx/allDays})))})))}))
            tiers))})))

(defn- cells
  "Every income tier, territory and code cell, in container order:
   [income label in not-in territory code quantities-of-code]."
  [quantities]
  (for [[income label in not-in] income-tiers
        [territory b-summer b-winter h-summer h-winter] quantities
        code codes]
    {:income income
     :label label
     :in in
     :not-in not-in
     :territory territory
     :code code
     :quantity (case code
                 "B" {:summer b-summer :winter b-winter}
                 "H" {:summer h-summer :winter h-winter})}))

(defn- cell-key [{:keys [income territory code]}]
  (str (name income) "-" (str/lower-case territory) "-" (str/lower-case code)))

(defn- cell-name [{:keys [label territory code]}]
  (str label ", Baseline Territory " territory ", Code " code))

(defn- profile-alternatives [id quantities]
  (let [c (id "pa-income-territory-code")]
    (dsl/profile-alternatives
     {:as c
      :name (:ladder-names prose)
      :has-alternative-dimensions
      (dsl/alternative-dimensions
       {:as ((u/ider c) "alternative-dimensions")
        :has-alternative-dimension
        [(dsl/alternative-dimension
          {:dimension-display-name "Program Enrollment"
           :dimension-property "https://urpx.org/ns/ontology/hasProgramEnrollment"
           :has-possible-values (dsl/rdf-list (for [[_ _ in] income-tiers
                                                    k in]
                                                (pge/program k)))})
         (dsl/alternative-dimension
          {:dimension-display-name "Baseline Territory"
           :custom-dimension-property "baselineTerritory"
           :has-possible-values (u/literal-list "xsd:string" (map first quantities))})
         (dsl/alternative-dimension
          {:dimension-display-name "Baseline Code"
           :custom-dimension-property "baselineCode"
           :has-possible-values (u/literal-list "xsd:string" codes)})]})
      :has-profile-alternative
      (vec (for [{:keys [in not-in territory code] :as cell} (cells quantities)
                 :let [pa (id "pa" (cell-key cell))
                       n (u/ider pa)]]
             (dsl/profile-alternative
              {:as pa
               :name (cell-name cell)
               :has-condition-expression
               (dsl/condition-expression
                {:as (n "condition-expression")
                 :root-node
                 (dsl/boolean-operation-node
                  {:as (n "root-node")
                   :operator :urpx/andOperator
                   :operand-nodes
                   (vec (concat
                         (for [k in]
                           (u/object-comparison (n (name k))
                                                :urpx/equalsOperator
                                                :urpx/hasProgramEnrollment
                                                (pge/program k)))
                         (for [k not-in]
                           (u/object-comparison (n (str "not-" (name k)))
                                                :urpx/notEqualsOperator
                                                :urpx/hasProgramEnrollment
                                                (pge/program k)))
                         [(u/custom-comparison (n "territory") "baselineTerritory" :string-value territory)
                          (u/custom-comparison (n "code") "baselineCode" :string-value code)]))})})})))})))

(defn- service-tiers [id quantities seasons]
  (let [brackets
        (fn [rung lower lower-op upper upper-op]
          (vec (for [cell (cells quantities)
                     [s] seasons
                     :let [q (get-in cell [:quantity s])]]
                 (dsl/service-bracket
                  {:as (id "bracket" rung (cell-key cell) s)
                   :applies-in-season (id "season" s)
                   :references-profile-alternative (id "pa" (cell-key cell))
                   :lower-bound (lower q)
                   :lower-bound-operator lower-op
                   :upper-bound (some-> upper (apply [q]))
                   :upper-bound-operator (when upper upper-op)}))))]
    (dsl/service-tiers
     {:as (id "tiers-baseline")
      :references-metric-input [(id "mi-energy-baseline")]
      :has-service-tier
      [(dsl/service-tier
        {:as (id "tier-baseline-t1")
         :name (:t1 tier-names)
         :service-tier-number 1
         :has-service-bracket (brackets "t1"
                                        (constantly 0M) :urpx/greaterThanOrEqualOperator
                                        identity :urpx/lessThanOrEqualOperator)})
       (dsl/service-tier
        {:as (id "tier-baseline-t2")
         :name (:t2 tier-names)
         :service-tier-number 2
         :has-service-bracket (brackets "t2"
                                        identity :urpx/greaterThanOperator
                                        over-baseline-multiple :urpx/lessThanOrEqualOperator)})
       (dsl/service-tier
        {:as (id "tier-baseline-t2c")
         :name (:t2c tier-names)
         :service-tier-number 3
         :has-service-bracket (brackets "t2c"
                                        over-baseline-multiple :urpx/greaterThanOperator
                                        nil nil)})]})))

(defn- metric-inputs [id credit]
  (let [energy (dsl/metric-specification
                {:as :pge/ms-energy
                 :measurement-kind :urpx/energy
                 :unit-of-measure :urpx/kWh})]
    (cond-> [(dsl/metric-input
              {:as (id "mi-energy")
               :name "kWh Energy Consumption Prices"
               :metric-input-type :urpx/measuredMetricInput
               :has-metric-specification energy})
             (dsl/metric-input
              {:as (id "mi-energy-baseline")
               :name "kWh Energy Consumption, baseline-tier reference metric"
               :metric-input-type :urpx/measuredMetricInput
               :has-metric-specification energy})
             (dsl/metric-input
              {:as (id "mi-meter-count")
               :name "Per Meter Prices"
               :metric-input-type :urpx/profileMetricInput
               :profile-metric-property :urpx/meterCount})]
      (seq credit) (conj (dsl/metric-input
                          {:as (id "mi-household-count")
                           :name "Per Household Prices"
                           :metric-input-type :urpx/profileMetricInput
                           :profile-metric-property :urpx/householdCount})))))

(defn- price-definitions [id credit tiers seasons]
  (let [number (into {}
                     (map (fn [[p _ _ _ n]] [p n]))
                     (periods tiers seasons))]
    (cond-> (conj (mapv (fn [[k n charge-type category portion ledger _ period]]
                          (dsl/price-definition
                           {:as (id "pd" k)
                            :name n
                            :charge-type charge-type
                            :charge-category category
                            :bill-portion portion
                            :tou-period-number (some-> period number)
                            :references-ledger (id "ledger" ledger)}))
                        charges)
                  (dsl/price-definition
                   {:as (id "pd-base-charge")
                    :name "Base Services Charge"
                    :charge-type :urpx/minimumBill
                    :charge-category :urpx/serviceCharge
                    :bill-portion :urpx/bundledPortion
                    :base-quantity 1
                    :has-calculation-method (u/per-day (id "pd-base-charge-calculation-method"))
                    :references-ledger (id "ledger-base-charge")}))
      (seq credit) (conj (dsl/price-definition
                          {:as (id "pd-climate-credit")
                           :name "California Climate Credit"
                           :charge-type :urpx/creditEnergy
                           :charge-category :urpx/environmental
                           :bill-portion :urpx/bundledPortion
                           :base-quantity 1
                           :has-applicability-rule
                           (dsl/applicability-rule
                            {:month (:months credit)})
                           :references-ledger (id "ledger-climate-credit")})))))

(defn- volumetric-prices
  "The Price keywords of every charge, in PriceDefinition order, the
   Conservation Incentive Adjustment as its three tier Prices."
  [ks]
  (mapcat (fn [k]
            (if (= k :cia)
              [:cia-t1 :cia-t2 :cia-t2c]
              [k]))
          ks))

(defn- prices [id date rate bsc credit quantities summaries]
  (let [set-of (fn [s]
                 (for [[k _ _ _ _ _ ps] charges
                       :when (= ps s)]
                   k))
        price (fn [k]
                (if-let [[_ rung] (re-matches #"cia-(t\w+)" (name k))]
                  (dsl/price
                   {:as (id "price" k)
                    :references-price-definition (id "pd-cia")
                    :name (str "Conservation Incentive Adjustment, " ((keyword k) tier-names))
                    :unit-price (rate k)
                    :service-tier-number ({"t1" 1 "t2" 2 "t2c" 3} rung)})
                  (dsl/price
                   {:as (id "price" k)
                    :references-price-definition (id "pd" k)
                    :name (some (fn [[ck n]] (when (= ck k) n)) charges)
                    :unit-price (rate k)})))
        summary (fn [program {:keys [excludes]} n]
                  (let [ks (remove (set excludes)
                                   (map first charges))]
                    (dsl/price-summary
                     {:as (id "summary" (str (name program) "-discountable"))
                      :name (u/fill (md/text n) {:count (count ks)})
                      :includes-price (mapv #(id "price" %)
                                            (volumetric-prices ks))})))
        price-set (fn [slug ks summary-nodes]
                    (dsl/price-set
                     {:as (id "ps" slug)
                      :start-date date
                      :has-price (mapv price ks)
                      :has-price-summary summary-nodes}))]
    (dsl/prices
     {:as (id "prices")
      :has-price (if (seq credit)
                   [(dsl/price
                     {:as (id "price-climate-credit")
                      :references-price-definition (id "pd-climate-credit")
                      :start-date date
                      :name "California Climate Credit"
                      :unit-price (:amount credit)})]
                   [])
      :has-price-set
      [(price-set "generation-charges"
                  (set-of :generation)
                  [(dsl/price-summary
                    {:as (id "summary-generation")
                     :name (md/text ::summary-generation)
                     :includes-price (mapv #(id "price" %) (set-of :generation))})])
       (price-set "distribution-charges" (set-of :distribution) nil)
       (price-set "conservation-incentive-adjustment" (volumetric-prices [:cia]) nil)
       (price-set "adjustment-charges"
                  (set-of :adjustment)
                  (not-empty (vec (for [[program s] (sort-by key summaries)]
                                    (summary program s (:name s))))))]
      :has-price-set-alternatives
      [(dsl/price-set-alternatives
        {:as (id "psa-bsc-by-income-tier")
         :name (:bsc-alternatives prose)
         :references-profile-alternatives (id "pa-income-territory-code")
         :has-price-set-alternative
         (vec (for [cell (cells quantities)
                    :let [k (cell-key cell)]]
                (dsl/price-set-alternative
                 {:as (id "psa-bsc" k)
                  :references-profile-alternative (id "pa" k)
                  :has-price
                  [(dsl/price
                    {:as (id "price-base-charge" k)
                     :references-price-definition (id "pd-base-charge")
                     :start-date date
                     :name (str "Base Services Charge, " (cell-name cell))
                     :unit-price (bsc (:income cell))})]})))})]})))

(defn- description [date {:keys [rate credit quantities tiers]}]
  (let [{:keys [vintage-pcia medical-baseline]} prose
        slots {:version (dsl/curie (version-id date))
               :peak-hours (let [[[_ _ _ [[_ start end]]]] tiers]
                             (tou/time-range start end))
               :territories (count quantities)
               :cells (* (count income-tiers) (count quantities) (count codes))
               :baseline-credit (u/plain (- (rate :cia-t2) (rate :cia-t1)))
               :climate-credit (some-> (:amount credit) u/amount)
               :climate-months (some->> (:months credit) (map u/xsd-gmonth) words/and-list)}]
    (str/join " "
              (keep #(some-> % (u/fill slots))
                    [(md/text ::version)
                     (md/dated ::baseline-credit date)
                     vintage-pcia
                     (md/dated ::change date)
                     medical-baseline
                     (md/dated ::climate-credit date)]))))

(defn- coverage-description [date {:keys [rate bsc quantities]}]
  (let [{:keys [text deferrals]} (as-of coverage date)
        [[_ p-summer]] quantities
        bscs (map (comp u/dollars bsc) [:care :fera :standard])
        slots {:version (dsl/curie (version-id date))
               :medical-baseline (dsl/curie (keyword "pge" (str "e-tou-c-medical-baseline-" date)))
               :date date
               :wildfire-fund (u/amount (rate :wildfire-fund))
               :bsc-and (words/and-list bscs)
               :bsc-slash (str/join " / " bscs)
               :standard-bsc (u/dollars (bsc :standard))
               :fera-bsc (u/dollars (bsc :fera))
               :medical-quantity (str (u/plain (:quantity (as-of pge/medical-quantity date))) " kWh")
               :p-summer (str (u/plain p-summer) " kWh")
               :p-summer-30 (str (u/plain (.stripTrailingZeros (* 30M p-summer))) " kWh")
               :cia-t2 (u/dollars (rate :cia-t2))}]
    (if text
      (u/fill (md/text text) slots)
      (md/deferral-coverage (map slots (:cites deferrals))))))

(defn- vintage-date
  "The date of the Vintaged PCIA table entry in effect on `date`."
  [date]
  (effective-key vintage-pcia-rates date))

(defn- vintage-id [vdate]
  (keyword "pge" (str "e-tou-c-vintage-pcia-" vdate)))

(defn- vintage-pcia
  "The Vintaged PCIA modifier version in effect on `date`, which applies to
   every base version that reads the same vintage table entry."
  [date]
  (let [vdate (vintage-date date)
        rates (vintage-pcia-rates vdate)
        years (sort (keys rates))
        filing (filings vdate)
        id (u/ider (vintage-id vdate))
        pa (id "pa-departure-vintage")
        credit-years (filter #(neg? (rates %)) years)
        {:keys [residential da-tbs]} vintage-pcia-prose]
    (dsl/rate-plan-modifier
     {:as :pge/e-tou-c-vintage-pcia
      :name "Vintaged Power Charge Indifference Adjustment (E-TOU-C)"
      :initial-effective-date "2009-01-01"
      :timezone-identifier (:timezone pge/pge)
      :modifier-unique-identifier "E-TOU-C-VPCIA"
      :has-rate-plan-modifier-version
      (dsl/rate-plan-modifier-version
       {:as (id)
        :modifier-version-number vdate
        :change-reason (:change-reason filing)
        :description (md/text ::vintage-pcia-description)
        :effective-date-time (u/xsd-date-time vdate)
        :price-currency "USD"
        :commodity [:urpx/electricity]
        :service-role :urpx/bundledServiceRole
        :applicable-to-rate-plan [:pge/e-tou-c]
        :applicable-to-rate-plan-version
        (vec (for [d (sort (keys filings))
                   :when (= vdate (vintage-date d))]
               (version-id d)))
        :has-data-source-reference
        [(u/data-source (assoc tariff :retrieved (:retrieved filing))
                        [8 8]
                        {:leaf-start "61131-E"
                         :leaf-end "61131-E"
                         :source-publication (pge/advice-letter-id (:advice-letter filing))})]
        :has-eligibility-rule
        [(u/customer-kind-rule (u/ider (id "er-residential"))
                               {:name "Residential customer"
                                :description residential
                                :customer-kind :urpx/residentialKind
                                :cx (id "cx-vpcia-residential")
                                :cn (id "cn-vpcia-residential")})
         (dsl/eligibility-rule
          {:as (id "er-da-tbs")
           :name "Generation service: DA or TBS"
           :description da-tbs
           :has-condition-expression
           (dsl/condition-expression
            {:as (id "cx-da-tbs")
             :root-node
             (dsl/boolean-operation-node
              {:as (id "bn-da-tbs-or")
               :operator :urpx/orOperator
               :operand-nodes (vec (for [k [:da :tbs]]
                                     (u/object-comparison (id "cn-program" k)
                                                          :urpx/equalsOperator
                                                          :urpx/hasProgramEnrollment
                                                          (pge/program k))))})})})]
        :has-plan-elements
        (dsl/plan-elements
         {:as (id "plan-elements")
          :has-metric-input
          [(dsl/metric-input
            {:as (id "mi-energy-vpcia")
             :name "kWh Energy Consumption"
             :metric-input-type :urpx/measuredMetricInput
             :has-metric-specification
             (dsl/metric-specification
              {:as :pge/ms-energy-vpcia
               :measurement-kind :urpx/energy
               :unit-of-measure :urpx/kWh})})]
          :has-billing-model
          (dsl/billing-model
           {:as (id "plan-elements-billing-model")
            :has-ledger
            [(u/ledger (id "ledger-vintage-pcia")
                       "Vintaged Power Charge Indifference Adjustment"
                       (id "mi-energy-vpcia"))]
            :has-price-definition
            [(dsl/price-definition
              {:as (id "pd-vintage-pcia")
               :name "Vintaged PCIA"
               :charge-type :urpx/strandedCosts
               :charge-category :urpx/adjustment
               :bill-portion :urpx/deliveryPortion
               :references-ledger (id "ledger-vintage-pcia")})]})
          :has-profile-alternatives
          [(dsl/profile-alternatives
            {:as pa
             :name "Vintaged PCIA \u2014 departure-vintage year"
             :has-alternative-dimensions
             (dsl/alternative-dimensions
              {:as ((u/ider pa) "alternative-dimensions")
               :has-alternative-dimension
               [(dsl/alternative-dimension
                 {:dimension-display-name "Departure Vintage Year"
                  :custom-dimension-property "departureVintage"
                  :has-possible-values (u/literal-list "xsd:gYear" years)})]})
             :has-profile-alternative
             (vec (for [y years
                        :let [k (str "vintage-" y)]]
                    (dsl/profile-alternative
                     {:as (id "pa" k)
                      :name (str "Departure vintage " y)
                      :has-condition-expression
                      (dsl/condition-expression
                       {:as (id "cx-pa" k)
                        :root-node (u/custom-comparison (id "cn-pa" k)
                                                        "departureVintage"
                                                        :g-year-value
                                                        (str y))})})))})]})
        :has-prices
        (dsl/prices
         {:as (id "prices")
          :has-price-set-alternatives
          [(dsl/price-set-alternatives
            {:as (id "psa-vpcia-by-vintage")
             :name "Vintaged PCIA \u2014 varies by departure-vintage year"
             :references-profile-alternatives pa
             :has-price-set-alternative
             (vec (for [y years]
                    (dsl/price-set-alternative
                     {:as (id "psa-vpcia" (str y))
                      :references-profile-alternative (id "pa" (str "vintage-" y))
                      :has-price
                      [(dsl/price
                        {:as (id "price-vpcia" (str y))
                         :references-price-definition (id "pd-vintage-pcia")
                         :start-date vdate
                         :name (str "Vintage PCIA \u2014 " y
                                    (when (neg? (rates y)) " (credit)"))
                         :unit-price (rates y)})]})))})]})
        :offered-by (u/utility-operator pge/pge)
        :for-rate-plan-modifier :pge/e-tou-c-vintage-pcia
        :has-coverage-claim
        (u/coverage-claim (keyword "pge" (str "cc-e-tou-c-vintage-pcia-" vdate))
                          :urpx/partial
                          {:evaluated-on (:evaluated-on filing)
                           :description
                           (u/fill (md/text ::vintage-pcia-coverage)
                                   {:count (words/number (count years))
                                    :first-rate (u/amount (rates (first years)))
                                    :first-year (first years)
                                    :credit (u/amount (rates (last years)))
                                    :credit-years (words/and-list (map str credit-years))})})})})))

(defn package
  "The @graph of version `date` of E-TOU-C: the package holding the plan and
   its Vintaged PCIA modifier, the programs it conditions on, and the advice
   letters and decision it cites."
  [{:keys [initial-effective-date] :as doc} date next]
  (dsl/dsl-scope
   {:outside (into {}
                   (for [d (keys filings)
                         :when (not= d date)]
                     [(version-id d) "urpx:RatePlanVersion"]))}
   (let [id (u/ider (version-id date))
         filing (filings date)
         ctx {:rate (as-of rates date)
              :bsc (as-of base-services-charge date)
              :credit (climate-credit date)
              :quantities (as-of baseline-quantities date)
              :tiers (as-of tou-tiers date)}
         {:keys [rate bsc credit quantities tiers]} ctx
         ss (as-of seasons date)
         letters (distinct [(:advice-letter (filings (first (sort (keys filings)))))
                            (:advice-letter filing)])
         vpcia (vintage-pcia date)]
     (into [(dsl/urpx-package
             {:as (keyword "pge" (str "doc-e-tou-c-" date))
              :target-urpx-version u/urpx-version
              :has-rate-plan
              [(dsl/rate-plan
                {:as :pge/e-tou-c
                 :name (:name doc)
                 :initial-effective-date initial-effective-date
                 :timezone-identifier (:timezone pge/pge)
                 :rate-plan-unique-identifier (:identifier doc)
                 :has-rate-plan-version
                 (dsl/rate-plan-version
                  {:as (id)
                   :description (description date ctx)
                   :effective-date-time (u/xsd-date-time date)
                   :expiration-date-time (some-> next u/xsd-date-time)
                   :change-reason (:change-reason filing)
                   :price-currency "USD"
                   :commodity [:urpx/electricity]
                   :service-role :urpx/bundledServiceRole
                   :customer-choice :urpx/voluntaryChoice
                   :is-default false
                   :has-data-source-reference
                   [(u/data-source (assoc tariff :retrieved (:retrieved filing))
                                   [1 10]
                                   {:leaf-start (first (:leaves filing))
                                    :leaf-end (second (:leaves filing))
                                    :source-publication (pge/advice-letter-id (:advice-letter filing))})]
                   :has-eligibility-rule
                   [(u/customer-kind-rule (u/ider (id "er-residential-tou-c"))
                                          {:name "Eligibility for E-TOU-C Residential Service"
                                           :description (md/text ::eligibility)
                                           :customer-kind :urpx/residentialKind
                                           :cx (id "cx-residential")
                                           :cn (id "cn-residential")})]
                   :has-plan-elements
                   (dsl/plan-elements
                    {:as (id "plan-elements")
                     :has-seasons (mapv (fn [[s n months]]
                                          (dsl/season
                                           {:as (id "season" s)
                                            :season-name n
                                            :month months}))
                                        ss)
                     :has-metric-input (metric-inputs id credit)
                     :has-billing-model
                     (dsl/billing-model
                      {:as (id "plan-elements-billing-model")
                       :has-tou-schedule [(tou-schedule id tiers ss)]
                       :has-service-tiers [(service-tiers id quantities ss)]
                       :has-ledger (vec (for [[k n t mi] ledgers
                                              :when (or (seq credit)
                                                        (not= k :climate-credit))]
                                          (dsl/ledger
                                           {:as (id "ledger" k)
                                            :name n
                                            :ledger-type t
                                            :references-metric-input [(id (name mi))]})))
                       :has-price-definition (price-definitions id credit tiers ss)})
                     :has-profile-alternatives (profile-alternatives id quantities)})
                   :has-prices (prices id date rate bsc credit quantities (as-of discountable date))
                   :has-modifier-options [:pge/e-tou-c-vintage-pcia]
                   :has-modifier-version-options
                   [(vintage-id (vintage-date date))]
                   :offered-by (u/utility-operator pge/pge)
                   :for-rate-plan :pge/e-tou-c
                   :has-rate-case (some-> (:decision filing) pge/decision-id)
                   :has-coverage-claim
                   (u/coverage-claim (keyword "pge" (str "cc-e-tou-c-" date))
                                     :urpx/partial
                                     {:evaluated-on (:evaluated-on filing)
                                      :description (coverage-description date ctx)})})})]
              :has-rate-plan-modifier [vpcia]})]
           (concat (pge/program-nodes)
                   (map pge/advice-letter-node letters)
                   (some-> (:decision filing) pge/decision-node vector))))))

(defurpx :rate-plans.kind/document e-tou-c
  {:kind :rate-plan
   :utility pge/pge
   :schedule "e-tou-c"
   :identifier "E-TOU-C"
   :name "Residential Time-Of-Use (Peak Pricing 4-9 p.m. Every Day)"
   :initial-effective-date "2019-03-01"
   :versions filings
   :expand package})
