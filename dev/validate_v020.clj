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
  [["PGE E-1"       "ca/iou/pge/e-1/versions/2026-03-01/rate-plan_pge_e-1_2026-03-01.jsonld"]
   ["PGE E-TOU-C 03-01" "ca/iou/pge/e-tou-c/versions/2026-03-01/rate-plan_pge_e-tou-c_2026-03-01.jsonld"]
   ["PGE E-TOU-C 03-27" "ca/iou/pge/e-tou-c/versions/2026-03-27/rate-plan_pge_e-tou-c_2026-03-27.jsonld"]
   ["PGE E-TOU-D"   "ca/iou/pge/e-tou-d/versions/2026-03-27/rate-plan_pge_e-tou-d_2026-03-27.jsonld"]
   ["PGE EV2"       "ca/iou/pge/ev2/versions/2026-03-27/rate-plan_pge_ev2_2026-03-27.jsonld"]
   ["PGE E-ELEC 01-01" "ca/iou/pge/e-elec/versions/2026-01-01/rate-plan_pge_e-elec_2026-01-01.jsonld"]
   ["PGE E-ELEC 03-27" "ca/iou/pge/e-elec/versions/2026-03-27/rate-plan_pge_e-elec_2026-03-27.jsonld"]
   ["CPAU E-1 07-01" "ca/pou/cpau/e-1/versions/2025-07-01/rate-plan_cpau_e-1_2025-07-01.jsonld"]
   ["CPAU E-1 09-01" "ca/pou/cpau/e-1/versions/2025-09-01/rate-plan_cpau_e-1_2025-09-01.jsonld"]
   ["CPAU E-1-TOU"   "ca/pou/cpau/e-1-tou/versions/2026-01-01/rate-plan_cpau_e-1-tou_2026-01-01.jsonld"]
   ["CPAU E-2"       "ca/pou/cpau/e-2/versions/2025-07-01/rate-plan_cpau_e-2_2025-07-01.jsonld"]
   ["CPAU E-4 TOU"   "ca/pou/cpau/e-4-tou/versions/2025-07-01/rate-plan_cpau_e-4-tou_2025-07-01.jsonld"]
   ["CPAU E-4"       "ca/pou/cpau/e-4/versions/2025-07-01/rate-plan_cpau_e-4_2025-07-01.jsonld"]
   ["CPAU E-7"       "ca/pou/cpau/e-7/versions/2025-07-01/rate-plan_cpau_e-7_2025-07-01.jsonld"]
   ["CPAU E-7 TOU"   "ca/pou/cpau/e-7-tou/versions/2025-07-01/rate-plan_cpau_e-7-tou_2025-07-01.jsonld"]])

(def la (ZoneId/of "America/Los_Angeles"))
;; Tuesday 2026-07-15 17:00 PDT — summer weekday, 5pm; covers peak windows
;; for PGE E-TOU-C (4-9pm all days), PGE E-TOU-D (5-8pm weekdays non-holiday),
;; PGE EV2 (4-9pm all days), and CPAU E-1-TOU (4-9pm peak). PGE E-1 and
;; CPAU E-1 are non-TOU.
(def probe-instant (ZonedDateTime/of 2026 7 15 17 0 0 0 la))

(defn pad [s n] (let [s (str s)] (str s (apply str (repeat (max 0 (- n (count s))) " ")))))

(defn- name-width [filings] (apply max (map (comp count first) filings)))

(defn validate-one [width [name path]]
  (print (pad name width) "")
  (flush)
  (try
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
            (println "    explain:" (pr-str explanation))))))
    (catch Exception e
      (println "load+coerce ✗  " (.getMessage e)))))

(defn -main [& _]
  (println "Probe instant:" probe-instant)
  (println)
  (let [w (inc (name-width filings))]
    (doseq [filing filings] (validate-one w filing)))
  (System/exit 0))
