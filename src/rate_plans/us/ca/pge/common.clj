;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.us.ca.pge.common
  "Pacific Gas and Electric Company: what its schedules share. The advice
   letters and decisions are keyed by their numbers; a later filing adds a
   key."
  (:require [clojure.string :as str]
            [rate-plans.defs]
            [rate-plans.urpx :as u]
            [urpx.defs :refer [defurpx]]
            [urpx.dsl :as dsl]))

(defurpx :rate-plans.kind/utility pge
  {:key "pge"
   :legal-name "Pacific Gas and Electric Company"
   :eia-id "14328"
   :prefix ["pge" "https://rate-plans.grid-coordination.energy/pge/"]
   :timezone "America/Los_Angeles"
   :path ["us" "ca" "pge" "electricity"]
   :context {"urpx:dimensionProperty" {"@type" "xsd:anyURI"}
             "urpx:gYearValue" {"@type" "xsd:gYear"}}})

(defurpx :rate-plans.kind/programs programs
  "The programs PG&E's schedules condition on, as urpx:ProgramEnrollment
   nodes pge:program-<key>."
  ;; key    name                                             program type
  [[:care  "California Alternate Rates for Energy (CARE)"  :urpx/lowIncomeProgram]
   [:fera  "Family Electric Rate Assistance (FERA)"         :urpx/moderateIncomeProgram]
   [:cca   "Community Choice Aggregation (CCA)"             :urpx/communityChoiceAggregation]
   [:da    "Direct Access (DA)"                             nil]
   [:tbs   "Transitional Bundled Service (TBS)"             nil]])

(defurpx :rate-plans.kind/advice-letters advice-letters
  "PG&E advice letters the filings cite, by number."
  {"7846-E" {:effective "2026-03-01"
             :received "2026-02-27"}
   "7869-E" {:effective "2026-03-27"
             :received "2026-03-27"
             :description "PG&E Advice Letter 7869-E under CPUC Decision D.26-03-013, reissuing Sheet 2 of the residential electric schedules effective {effective}. The changes it makes differ by schedule and are described on each urpx:RatePlanVersion."}
   "7921-E" {:effective "2026-06-01"
             :received "2026-06-01"
             :description "PG&E Advice Letter 7921-E under CPUC Decision D.26-04-036, reissuing Sheet 1 of Schedule E-1 and Sheet 2 of Schedules E-TOU-C, E-TOU-D, EV2 and E-ELEC effective {effective} to state the California Climate Credit as a semi-annual payment in the August and September bill cycles."}})

(defurpx :rate-plans.kind/decisions decisions
  "CPUC decisions the filings cite, by number."
  {"D.26-03-013" {:url "https://docs.cpuc.ca.gov/PublishedDocs/Published/G000/M603/K306/603306591.PDF"}
   "D.26-04-036" {:url "https://docs.cpuc.ca.gov/PublishedDocs/Published/G000/M605/K823/605823091.PDF"
                  :description "Decision Ordering Immediate Improvements to the California Climate Credit, Rulemaking 25-07-013, adopted April 30, 2026. The url is the proposed decision the CPUC's announcement of the vote links as the proposal approved."}})

(defurpx :rate-plans.kind/dollars medical-quantity
  "Electric Rule 19 Part A, the Standard Medical Baseline Quantity in kWh per
   day, as printed for hand calculation."
  {"2023-03-23" {:quantity 16.438M}})

;; ---------------------------------------------------------------------------
;; IRIs and nodes
;; ---------------------------------------------------------------------------

(defn program
  "The IRI keyword of program `k`, e.g. :pge/program-care."
  [k]
  (keyword "pge" (str "program-" (name k))))

(defn advice-letter-id
  "\"7846-E\" -> :pge/al-7846-e."
  [number]
  (keyword "pge" (str "al-" (str/lower-case number))))

(defn decision-id
  "\"D.26-03-013\" -> :pge/rc-d-26-03-013."
  [number]
  (keyword "pge" (str "rc-" (str/lower-case (str/replace number "." "-")))))

(defn program-nodes []
  (for [[k n t] programs]
    (dsl/program-enrollment
     {:as (program k)
      :program-name n
      :program-type t})))

(defn advice-letter-node [number]
  (let [{:keys [effective received description]} (advice-letters number)]
    (dsl/source-publication
     {:as (advice-letter-id number)
      :name (str "PG&E Advice Letter " number)
      :filing-number number
      :issuing-authority "California Public Utilities Commission"
      :publication-type :urpx/tariffSupplement
      :description (some-> description
                           (u/fill {:effective effective}))
      :effective-date effective
      :date-received received})))

(defn decision-node [number]
  (let [{:keys [url description]} (decisions number)]
    (dsl/rate-case
     {:as (decision-id number)
      :case-number number
      :name (str "CPUC Decision " number)
      :description description
      :url url})))
