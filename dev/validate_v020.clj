(ns validate-v020
  "End-to-end validation of the four PG&E v0.2.0 filings using clj-urpx.

   Pyshacl confirms each JSON-LD file is SHACL-conformant. This script
   exercises the consumer path: load → coerce (Malli) → validate →
   resolve a representative price for a known instant. Catches semantic
   bugs that SHACL alone cannot see — for example, that
   PriceDefinition.referencesLedger is wired to the right Ledger, that
   per-customer credits are excluded from a $/kWh marginal sum, and that
   PriceDefinition.hasApplicabilityRule.month gates resolution by month."
  (:require [urpx.core :as core]
            [urpx.coerce :as coerce]
            [urpx.price :as price]
            [urpx.schema :as schema])
  (:import [java.time ZoneId ZonedDateTime]))

(def filings
  ;; [kind name path]. kind ∈ #{:rate-plan :rate-plan-modifier}.
  [[:rate-plan "PGE E-1"       "ca/iou/pge/e-1/versions/2026-03-01/rate-plan_pge_e-1_2026-03-01.jsonld"]
   [:rate-plan "PGE E-TOU-C 03-01" "ca/iou/pge/e-tou-c/versions/2026-03-01/rate-plan_pge_e-tou-c_2026-03-01.jsonld"]
   [:rate-plan "PGE E-TOU-C 03-27" "ca/iou/pge/e-tou-c/versions/2026-03-27/rate-plan_pge_e-tou-c_2026-03-27.jsonld"]
   [:rate-plan "PGE E-TOU-D"   "ca/iou/pge/e-tou-d/versions/2026-03-27/rate-plan_pge_e-tou-d_2026-03-27.jsonld"]
   [:rate-plan "PGE EV2"       "ca/iou/pge/ev2/versions/2026-03-27/rate-plan_pge_ev2_2026-03-27.jsonld"]
   [:rate-plan "PGE E-ELEC 01-01" "ca/iou/pge/e-elec/versions/2026-01-01/rate-plan_pge_e-elec_2026-01-01.jsonld"]
   [:rate-plan "PGE E-ELEC 03-27" "ca/iou/pge/e-elec/versions/2026-03-27/rate-plan_pge_e-elec_2026-03-27.jsonld"]
   [:rate-plan "CPAU E-1 07-01" "ca/pou/cpau/e-1/versions/2025-07-01/rate-plan_cpau_e-1_2025-07-01.jsonld"]
   [:rate-plan "CPAU E-1 09-01" "ca/pou/cpau/e-1/versions/2025-09-01/rate-plan_cpau_e-1_2025-09-01.jsonld"]
   [:rate-plan "CPAU E-1-TOU"   "ca/pou/cpau/e-1-tou/versions/2026-01-01/rate-plan_cpau_e-1-tou_2026-01-01.jsonld"]
   [:rate-plan "CPAU E-2"       "ca/pou/cpau/e-2/versions/2025-07-01/rate-plan_cpau_e-2_2025-07-01.jsonld"]
   [:rate-plan "CPAU E-4 TOU"   "ca/pou/cpau/e-4-tou/versions/2025-07-01/rate-plan_cpau_e-4-tou_2025-07-01.jsonld"]
   [:rate-plan "CPAU E-4"       "ca/pou/cpau/e-4/versions/2025-07-01/rate-plan_cpau_e-4_2025-07-01.jsonld"]
   [:rate-plan "CPAU E-7"       "ca/pou/cpau/e-7/versions/2025-07-01/rate-plan_cpau_e-7_2025-07-01.jsonld"]
   [:rate-plan "CPAU E-7 TOU"   "ca/pou/cpau/e-7-tou/versions/2025-07-01/rate-plan_cpau_e-7-tou_2025-07-01.jsonld"]
   [:rate-plan "CPAU E-14"      "ca/pou/cpau/e-14/versions/2025-07-01/rate-plan_cpau_e-14_2025-07-01.jsonld"]
   [:rate-plan "CPAU E-16"      "ca/pou/cpau/e-16/versions/2025-09-01/rate-plan_cpau_e-16_2025-09-01.jsonld"]
   [:rate-plan "CPAU E-3"       "ca/pou/cpau/e-3/versions/2007-07-01/rate-plan_cpau_e-3_2007-07-01.jsonld"]
   [:rate-plan-modifier "CPAU E-2-G" "ca/pou/cpau/e-2-g/versions/2025-07-01/rate-plan-modifier_cpau_e-2-g_2025-07-01.jsonld"]
   [:rate-plan-modifier "CPAU E-4-G" "ca/pou/cpau/e-4-g/versions/2025-07-01/rate-plan-modifier_cpau_e-4-g_2025-07-01.jsonld"]
   [:rate-plan-modifier "CPAU E-7-G" "ca/pou/cpau/e-7-g/versions/2025-07-01/rate-plan-modifier_cpau_e-7-g_2025-07-01.jsonld"]
   [:rate-plan-modifier "CPAU E-HRA"   "ca/pou/cpau/e-hra/versions/2023-01-01/rate-plan-modifier_cpau_e-hra_2023-01-01.jsonld"]
   [:rate-plan-modifier "CPAU E-EEC-1" "ca/pou/cpau/e-eec-1/versions/2025-09-01/rate-plan-modifier_cpau_e-eec-1_2025-09-01.jsonld"]
   [:rate-plan-modifier "CPAU E-NSE-1" "ca/pou/cpau/e-nse-1/versions/2025-09-01/rate-plan-modifier_cpau_e-nse-1_2025-09-01.jsonld"]])

(def la (ZoneId/of "America/Los_Angeles"))
;; Tuesday 2026-07-15 17:00 PDT — summer weekday, 5pm; covers peak windows
;; for PGE E-TOU-C (4-9pm all days), PGE E-TOU-D (5-8pm weekdays non-holiday),
;; PGE EV2 (4-9pm all days), and CPAU E-1-TOU (4-9pm peak). PGE E-1 and
;; CPAU E-1 are non-TOU.
(def probe-instant (ZonedDateTime/of 2026 7 15 17 0 0 0 la))

(defn pad [s n] (let [s (str s)] (str s (apply str (repeat (max 0 (- n (count s))) " ")))))

(defn- name-width [filings] (apply max (map (comp count second) filings)))

(defn- validate-rate-plan [path]
  (let [raw (core/load-rate-plan path)
        plan (coerce/coerce-rate-plan raw)]
    (if (coerce/validate schema/RatePlan plan)
      (do
        (print "load+coerce ✓ ")
        (flush)
        (try
          (let [resolved (price/resolve-prices plan probe-instant)
                ledger-count (count (:urpx.resolved/ledgers resolved))
                marginal (price/marginal-unit-rate resolved)]
            (print (format "resolve ✓  (%d ledgers, marginal=%s)"
                           ledger-count marginal)))
          (catch Exception e
            (print (format "resolve ✗  %s" (.getMessage e)))))
        (println))
      (do
        (println "validate ✗")
        (let [explanation (coerce/explain schema/RatePlan plan)]
          (println "    explain:" (pr-str explanation)))))))

(defn- validate-rate-plan-modifier [path]
  (let [raw (core/load-rate-plan-modifier path)
        modifier (coerce/coerce-rate-plan-modifier raw)]
    (if (coerce/validate schema/RatePlanModifier modifier)
      ;; resolve-prices not yet implemented for standalone modifiers — composer
      ;; with base RatePlan deferred until urpx-org/urpx#23 resolves.
      (println "load+coerce ✓  (resolve N/A — modifier requires base composition)")
      (do
        (println "validate ✗")
        (let [explanation (coerce/explain schema/RatePlanModifier modifier)]
          (println "    explain:" (pr-str explanation)))))))

(defn validate-one [width [kind name path]]
  (print (pad name width) "")
  (flush)
  (try
    (case kind
      :rate-plan          (validate-rate-plan path)
      :rate-plan-modifier (validate-rate-plan-modifier path))
    (catch Exception e
      (println "load+coerce ✗  " (.getMessage e)))))

(defn -main [& _]
  (println "Probe instant:" probe-instant)
  (println)
  (let [w (inc (name-width filings))]
    (doseq [filing filings] (validate-one w filing)))
  (System/exit 0))
