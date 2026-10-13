;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.us.ca.pge.e-tou-c
  "PG&E Schedule E-TOU-C, Residential Time-Of-Use (Peak Pricing 4-9 p.m.
   Every Day), and its Vintaged PCIA modifier, which each base version's
   document carries. Every table is keyed by the date it takes effect; a
   later filing adds a key."
  (:require [clojure.string :as str]
            [rate-plans.defs :refer [as-of]]
            [rate-plans.urpx :as u]
            [rate-plans.us.ca.pge.common :as pge]
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

(defn tier-iri
  "The IRI of baseline tier `rung` (t1, t2, t2c) of version `date`."
  [date rung]
  (dsl/curie ((u/ider (version-id date)) "tier-baseline" rung)))

(defn price-iri
  "The IRI of the Price of charge `k` in version `date`."
  [date k]
  (dsl/curie ((u/ider (version-id date)) "price" k)))

;; ---------------------------------------------------------------------------
;; Prose
;; ---------------------------------------------------------------------------

(defurpx :rate-plans.kind/description prose
  {:version
   (str "Voluntary residential TOU schedule with summer/winter peak ({peak-hours} all days) and off-peak periods. "
        "Customers pay a daily base services charge that varies by income tier (CARE / FERA / standard). "
        "The Conservation Incentive Adjustment is priced on {version}-tiers-baseline: Tier 1 up to the Special Condition 1 baseline quantity, Tier 2 to four times it and Tier 2 Continued above that, in kWh per day for each of the {territories} baseline territories, Code B (basic) and Code H (all-electric), and both seasons. "
        "The territory and code share one urpx:ProfileAlternatives with the income tier, {version}-pa-income-territory-code, whose {cells} members are the cells of the three dimensions; each urpx:ServiceBracket names one cell and one season.")
   :vintage-pcia "Vintage PCIA for CCA/DA/TBS customers is modeled as a sibling RatePlanModifier in this file."
   :medical-baseline "The Standard Medical Baseline Quantity of Electric Rule 19 (Code M and Code S) is the modifier pge:e-tou-c-medical-baseline, a second document in this filing's directory."
   :baseline-credit
   {"2026-03-01" "Sheet 2\u2019s Baseline Credit of (${baseline-credit}) on baseline usage is the difference between Sheet 3\u2019s two CIA rates, so that pair carries it and it is not priced again."}
   :change
   {"2026-03-27" "Compared to the 2026-03-01 version: California Climate Credit removed (Sheet 2 reissued under AL 7869-E / D.26-03-013, sheet 61249-E)."
    "2026-06-01" "Compared to the 2026-03-27 version: Sheet 2 (61364-E) is reissued under AL 7921-E / D.26-04-036 with the California Climate Credit restored, in the August and September bill cycles; no other price moved."}
   :climate-credit
   {"2026-06-01" "The California Climate Credit, (${climate-credit}) per household as a semi-annual payment in the August and September bill cycles, is in this version, priced in calendar months {climate-months} on a urpx:householdCount MetricInput."}
   :eligibility "Voluntary, opt-in. Single-phase or polyphase residential service in single-family dwellings, separately metered flats and apartments, common-area accounts in multifamily complexes, and farm service on residential premises."
   :ladder-names
   "Income tier (CARE / FERA / standard) by Baseline Territory and Baseline Code (Sheet 1 RATES; Special Condition 1, Sheet 5)"
   :bsc-alternatives
   "Base Services Charge by income tier (CARE / FERA / standard), one alternative per income tier, Baseline Territory and Baseline Code cell"
   :summary-generation
   "Generation subtotal for E-TOU-C: its generation Prices and its Bundled Power Charge Indifference Adjustment. Schedule E-TOU-C Sheet 8 (Cal. P.U.C. Sheet 61131-E): Direct Access and Community Choice Aggregation Generation Service Customers \"shall pay all charges shown in the Unbundling of Total Rates except for the Bundled Power Charge Indifference Adjustment and the generation charge\". pge:cca-crs offsets this subtotal for Community Choice Aggregation customers."})

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
           :name "CARE-discountable subtotal for E-TOU-C. The {count} volumetric charges, the Conservation Incentive Adjustment counted once across its three baseline tiers, the Schedule D-CARE percentage discount applies to: \"total bundled volumetric charges less charges from which they are exempt\" (Sheet 1). Excludes the Wildfire Fund Charge, the Wildfire Hardening Charge, the Recovery Bond Charge and the Recovery Bond Credit, and the base services charge, which is not volumetric. The Public Purpose Programs charge is included whole: Sheet 1 also exempts its CARE surcharge portion, which the base schedule does not publish."}
    :fera {:excludes [:wildfire-hardening :recovery-bond :recovery-bond-credit]
           :name "FERA-discountable subtotal for E-TOU-C. The {count} volumetric charges, the Conservation Incentive Adjustment counted once across its three baseline tiers, the Schedule E-FERA percentage discount applies to: \"total bundled volumetric charges\", generation included, \"after FERA customers are exempted from the Wildfire Hardening Charge, Recovery Bond Charge, and the Recovery Bond Credit\" (Sheet 1). Excludes those three and the base services charge, which is not volumetric. Unlike CARE, the Wildfire Fund Charge is inside this subtotal."}}})

(defurpx :rate-plans.kind/coverage coverage
  "Each version's coverage evaluation. From 2026-03-27 it lists the filing's
   tariff.toml [modeling].deferrals in the same words."
  {"2026-03-01"
   {:text "Five parts of the published Schedule E-TOU-C are not represented in this filing. The Special Condition 8 bill protection, which for twelve months after enrollment credits the customer the difference between what it paid on this schedule and what it would have paid on the tiered non-time-of-use Schedule E-1, with its own exclusions (customers on Schedules NEM2, NEM2V or NEM2VMSH who start or transfer service on or after October 1, 2020, customers opting in from another time-of-use plan, and customers requesting enrollment after May 4, 2022) and a parallel twelve-month version on Sheet 9 covering the non-generation charges of community choice aggregation and direct access customers. The CARE half of the Wildfire Fund Charge exemption: Special Condition 11 excludes CARE and medical baseline sales from the charge, and the medical baseline half is pge:e-tou-c-medical-baseline-{date}, but pge:d-care's exemption names the 2026-03-27 version's Price, so a CARE customer under this version is priced ${wildfire-fund} per kWh. The Sheet 4 unbundling of the base services charge into its Distribution, Public Purpose Program, Nuclear Decommissioning and New System Generation components for each income tier; only the three daily totals ({bsc-and}) are modeled. The second qualification path for Income Tier 2, an affordable rental unit in a property listed in the California Housing Partnership's database and restricted to residents at or below 80 percent of Area Median Income; only the FERA path is modeled, so a customer qualifying through affordable housing alone resolves to the Tier 3 charge. And the Sheet 1 instruction that time-of-use period usage be assigned to baseline tiers pro rata, so that a customer with twenty percent of its usage in the peak period has twenty percent of the usage in each tier treated as on-peak: this filing carries both the time-of-use dimension and the baseline tiers, but nothing states how the two combine. Three things are out of scope rather than missing. The standby reservation charges the Applicability section imports from Schedule S Special Conditions 1 through 6 for customers partly supplied from a nonutility source are charges of another schedule, and with them go the Special Condition 9 and 10 exemptions for sub-megawatt non-exporting solar and for distributed energy resources. Special Condition 6's designation of a primary meter and additional meters, and Special Condition 7's one-time option for a separately metered common-area account to move to a general service schedule, are customer-service procedures and not rates."}
   "2026-03-27"
   {:deferrals
    ["Schedule E-TOU-C Sheet 8 (Cal. P.U.C. Sheet 61131-E): Direct Access and Transitional Bundled Service customers 'shall pay all charges shown in the Unbundling of Total Rates except for the Bundled Power Charge Indifference Adjustment and the generation charge', paying their Vintaged PCIA instead. pge:e-tou-c-vintage-pcia is gated on DA and TBS and adds the vintaged rate, but nothing removes this version's generation Prices or its Bundled PCIA Price, so base plus pge:e-tou-c-vintage-pcia still charges a DA or TBS customer PG&E generation and both the bundled and the vintaged PCIA. The DA and TBS offset waits on Schedule DA-CRS. Community Choice Aggregation customers are priced by base plus pge:cca-crs, whose multiplier -1 Price offsets {version}-summary-generation."
     "Sheet 4 prices the Base Services Charge by component, per income tier, $ per customer per day: Distribution (-$0.10751 / -$0.02710 / $0.36945), Public Purpose Program ($0.19131 / $0.31065 / $0.31065), Nuclear Decommissioning ($0.00000 all tiers), New System Generation Charge ($0.11333 all tiers). The model carries only the three Sheet 2 bundled totals ({bsc-slash}), which the components sum to exactly, so no number is wrong today. What is lost is the delivery-versus-supply split of the fixed charge, which is what Sheet 8's CCA/DA treatment needs, and the model already unbundles the energy side this way. Expressible now: three more PriceDefinitions, each with a three-alternative PriceSetAlternatives mirroring the existing Base Services Charge structure."
     "Rule 19 Part F: \"If PG&E finds that you need more than the standard {medical-quantity} kWh per day, it will increase your daily Medical Baseline Quantity. In determining how many Additional Quantities you will be assigned, PG&E will round its calculation of your total daily kWh medical needs up to the nearest increment of {medical-quantity} kWh.\" pge:e-tou-c-medical-baseline-{date} carries one Standard Medical Baseline Quantity. An additional quantity is a per-customer multiple PG&E assigns, so it is a customer attribute rather than a tariff figure; it is expressible as further adjusting brackets once a multiple is chosen, and nothing in this corpus chooses one."
     "Sheet 1 defines Income Tier 2 by two disjuncts: (a) FERA-eligible households, or (b) residents of an affordable rental unit in a property listed in the California Housing Partnership's database and restricted to incomes at or below 80 percent of Area Median Income. The tier-2 ProfileAlternative gates only on hasProgramEnrollment = pge:program-fera, so a qualifying (b) customer resolves to Income Tier 3 and is billed ${standard-bsc} per customer per day where the schedule prices ${fera-bsc}. Expressible now as an orOperator disjunct over a CustomOperandNode, the construct this file's vintage-PCIA alternatives already use for customConditionProperty 'departureVintage'."
     "Sheet 1, RATES: 'TOU period usage is assigned to tiers on a pro-rated basis. For example, if twenty percent of a customer's usage is in the peak period, then twenty percent of the total usage in each tier will be treated as on-peak usage.' This is the rule composing this version's TOU dimension with its baseline tiers, and neither is stated to depend on the other. Under v0.5.1, CalculationMethodShape is sh:closed and the only slot is the free-text calculationFormula, so the rule can be recorded as prose but not as a computable composition. Standard-level, not a modeling oversight."
     "Sheet 3's line item New System Generation Charge (all usage), $0.00000 per kWh, has no PriceDefinition and no Price. Zero-valued, so no bill is wrong and the 20 modeled components still reconstruct the Sheet 2 totals, but the unbundled component list is incomplete against the sheet and the omission becomes a wrong number the first time PG&E sets the charge nonzero."
     "Special Condition 1 (Sheet 5, Cal. P.U.C. Sheet 61128-E) publishes the baseline quantities as kWh PER DAY. {version}-mi-energy-baseline declares unitOfMeasure urpx:kWh with no intervalDuration, so a bracket bound of {p-summer} reads as {p-summer} kWh rather than {p-summer} kWh per day; on a 30-day summer bill in territory P the real Tier 1 ceiling is {p-summer-30} kWh. v0.5.1 MetricSpecificationShape carries urpx:intervalDuration (xsd:duration, maxCount 1), so P1D is expressible. Put the interval there and not on a PriceDefinition's CalculationMethod, where an interval states the window a charge is calculated over rather than the period the baseline quantity is published in."
     "The schedule draws one usage boundary, baseline versus over baseline: Sheet 2's 'Applied to Baseline Usage Only' and the two Sheet 3 Conservation Incentive Adjustment lines. This version asserts a third tier, {version}-tier-baseline-t2c 'above four times the Special Condition 1 quantity', and caps tier 2 at exactly 4x the Special Condition 1 quantity in every cell. Nothing in the ten sheets states 400 percent, four times, or a second over-baseline tier. Both tiers price at ${cia-t2} so the split is economically inert, but it publishes a boundary this filing does not. Either cite the source for the 4x figure or collapse Tier 2 and Tier 2 Continued."]}})

(defurpx :rate-plans.kind/description vintage-pcia-prose
  {:description "Vintaged Power Charge Indifference Adjustment (per kWh) applied to Transitional Bundled Service (TBS) and Direct Access (DA) customers on Schedule E-TOU-C. Replaces the Bundled PCIA for these customers; the applicable rate is determined by the customer's bundled-service departure vintage year. Community Choice Aggregation (CCA) customers take the same rates from pge:cca-crs."
   :residential "Vintaged PCIA applies only to residential customers."
   :da-tbs "Vintaged PCIA under this modifier applies to customers taking Direct Access service or Transitional Bundled Service. Community Choice Aggregation customers take it from pge:cca-crs."
   :coverage "This modifier carries the {count} vintage Power Charge Indifference Adjustment rates published on Schedule E-TOU-C Sheet 8, from ${first-rate} per kWh for the {first-year} vintage to a credit of ${credit} per kWh for the {credit-years} vintages, gated on a residential customer taking Direct Access or Transitional Bundled Service. Community Choice Aggregation customers take the same {count} rates from pge:cca-crs. Sheet 8 states that Direct Access and Transitional Bundled Service customers pay every charge in the Unbundling of Total Rates except the Bundled Power Charge Indifference Adjustment and the generation charge, and nothing in this modifier removes the base plan's generation Prices or its Bundled PCIA, so a consumer applying the base plan together with this modifier charges a Direct Access or Transitional Bundled Service customer PG&E generation and both the bundled and the vintaged adjustment. Three further charges the same sheet directs these customers to are absent because they live in other schedules: the franchise fee surcharge under Schedule E-FFS for Direct Access customers, the short-term commodity prices under Schedule TBCC for Transitional Bundled Service customers, and the exemptions set out in Schedule DA CRS."})

;; ---------------------------------------------------------------------------
;; Words from the tables
;; ---------------------------------------------------------------------------

(defn- dollars
  "0.05354M -> \"0.05354\"; the sign is the caller's."
  [^BigDecimal d]
  (u/plain (.abs d)))

(defn- hour
  "\"16:00\" -> 4, \"21:00\" -> 9."
  [hhmm]
  (let [h (mod (parse-long (subs hhmm 0 2)) 12)]
    (if (zero? h) 12 h)))

(defn- peak-hours
  "\"4-9 p.m.\" from the peak tier's one bracket."
  [tiers]
  (let [[_ _ _ [[_ start end]]] (first tiers)]
    (str (hour start)
         "-"
         (hour end)
         (if (< (parse-long (subs end 0 2)) 12) " a.m." " p.m."))))

(def ^:private number-words
  ["zero" "one" "two" "three" "four" "five" "six" "seven" "eight" "nine" "ten"
   "eleven" "twelve" "thirteen" "fourteen" "fifteen" "sixteen" "seventeen"
   "eighteen" "nineteen" "twenty"])

(defn- gmonth [m]
  (format "--%02d" m))

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
  (let [c (id "pa-income-territory-code")
        string-list (fn [xs]
                      (dsl/rdf-list (for [x xs]
                                      {:jsonld/value x
                                       :jsonld/type "xsd:string"})))]
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
           :has-possible-values (string-list (map first quantities))})
         (dsl/alternative-dimension
          {:dimension-display-name "Baseline Code"
           :custom-dimension-property "baselineCode"
           :has-possible-values (string-list codes)})]})
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
                      :name (u/fill n {:count (count ks)})
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
                     :name (:summary-generation prose)
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
  (let [{:keys [version vintage-pcia medical-baseline baseline-credit change climate-credit]} prose
        words {:version (dsl/curie (version-id date))
               :peak-hours (peak-hours tiers)
               :territories (count quantities)
               :cells (* (count income-tiers) (count quantities) (count codes))
               :baseline-credit (u/plain (- (rate :cia-t2) (rate :cia-t1)))
               :climate-credit (some-> (:amount credit) dollars)
               :climate-months (some->> (:months credit) (map gmonth) u/and-list)}]
    (str/join " "
              (keep #(some-> % (u/fill words))
                    [version
                     (baseline-credit date)
                     vintage-pcia
                     (change date)
                     medical-baseline
                     (climate-credit date)]))))

(defn- coverage-description [date {:keys [rate bsc quantities]}]
  (let [{:keys [text deferrals]} (as-of coverage date)
        [[_ p-summer]] quantities
        words {:version (dsl/curie (version-id date))
               :date date
               :wildfire-fund (dollars (rate :wildfire-fund))
               :bsc-and (u/and-list (map #(str "$" (dollars (bsc %))) [:care :fera :standard]))
               :bsc-slash (str/join " / " (map #(str "$" (dollars (bsc %))) [:care :fera :standard]))
               :standard-bsc (dollars (bsc :standard))
               :fera-bsc (dollars (bsc :fera))
               :medical-quantity (u/plain (:quantity (as-of pge/medical-quantity date)))
               :p-summer p-summer
               :p-summer-30 (u/plain (.stripTrailingZeros (* 30M p-summer)))
               :cia-t2 (dollars (rate :cia-t2))}]
    (if text
      (u/fill text words)
      (str "This filing does not carry everything its source document states. "
           (count deferrals)
           " parts are deferred, listed here in the same words as the filing's tariff.toml [modeling].deferrals so the two records cannot drift. "
           (str/join " "
                     (map-indexed (fn [i d]
                                    (str "(" (inc i) ") " (u/fill d words)))
                                  deferrals))))))

(defn- vintage-date
  "The date of the Vintaged PCIA table entry in effect on `date`."
  [date]
  (some (fn [d]
          (when (<= (compare d date) 0)
            d))
        (sort #(compare %2 %1) (keys vintage-pcia-rates))))

(defn- vintage-id [vdate]
  (keyword "pge" (str "e-tou-c-vintage-pcia-" vdate)))

(defn- vintage-pcia
  "The Vintaged PCIA modifier version in effect on `date`, which applies to
   every base version that reads the same vintage table entry."
  [date operator]
  (let [vdate (vintage-date date)
        rates (vintage-pcia-rates vdate)
        years (sort (keys rates))
        filing (filings vdate)
        id (u/ider (vintage-id vdate))
        pa (id "pa-departure-vintage")
        credit-years (filter #(neg? (rates %)) years)
        {:keys [description residential da-tbs] :as words} vintage-pcia-prose]
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
        :description description
        :effective-date-time (str vdate "T00:00:00")
        :price-currency "USD"
        :commodity [:urpx/electricity]
        :service-role :urpx/bundledServiceRole
        :applicable-to-rate-plan [:pge/e-tou-c]
        :applicable-to-rate-plan-version
        (vec (for [d (sort (keys filings))
                   :when (= vdate (vintage-date d))]
               (u/ref (dsl/curie (version-id d)))))
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
                  :has-possible-values (dsl/rdf-list (for [y years]
                                                       {:jsonld/value (str y)
                                                        :jsonld/type "xsd:gYear"}))})]})
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
        :offered-by operator
        :for-rate-plan-modifier :pge/e-tou-c-vintage-pcia
        :has-coverage-claim
        (u/coverage-claim (keyword "pge" (str "cc-e-tou-c-vintage-pcia-" vdate))
                          :urpx/partial
                          {:evaluated-on (:evaluated-on filing)
                           :description
                           (u/fill (:coverage words)
                                   {:count (number-words (count years))
                                    :first-rate (dollars (rates (first years)))
                                    :first-year (first years)
                                    :credit (dollars (rates (last years)))
                                    :credit-years (u/and-list (map str credit-years))})})})})))

(defn package
  "The @graph of version `date` of E-TOU-C: the package holding the plan and
   its Vintaged PCIA modifier, the programs it conditions on, and the advice
   letters and decision it cites."
  [{:keys [initial-effective-date] :as doc} date next]
  (dsl/dsl-scope
   (let [id (u/ider (version-id date))
         filing (filings date)
         ctx {:rate (as-of rates date)
              :bsc (as-of base-services-charge date)
              :credit (climate-credit date)
              :quantities (as-of baseline-quantities date)
              :tiers (as-of tou-tiers date)}
         {:keys [rate bsc credit quantities tiers]} ctx
         ss (as-of seasons date)
         operator (u/utility-operator pge/pge)
         letters (distinct [(:advice-letter (filings (first (sort (keys filings)))))
                            (:advice-letter filing)])
         vpcia (vintage-pcia date operator)]
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
                   :effective-date-time (str date "T00:00:00")
                   :expiration-date-time (some-> next (str "T00:00:00"))
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
                                           :description (:eligibility prose)
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
                   :offered-by operator
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
