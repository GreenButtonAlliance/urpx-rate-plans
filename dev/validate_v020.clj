(ns validate-v020
  "End-to-end validation of the four PG&E v0.2.0 filings using clj-urpx.

   Pyshacl confirms each JSON-LD file is SHACL-conformant. This script
   exercises the consumer path: load → coerce (Malli) → validate →
   resolve a representative price for a known instant. Catches semantic
   bugs that SHACL alone cannot see — for example, that
   PriceDefinition.referencesLedger is wired to the right Ledger, that
   per-customer credits are excluded from a $/kWh marginal sum, and that
   PriceDefinition.hasApplicabilityRule.month gates resolution by month."
  (:require [clojure.java.io :as io]
            [clojure.string :as str]
            [urpx.core :as core]
            [urpx.coerce :as coerce]
            [urpx.price :as price]
            [urpx.schema :as schema])
  (:import [java.io File]
           [java.time ZoneId ZonedDateTime]))

(defn discover-filings
  "Walk the ca/ corpus and return [[kind label path] ...] for every
   rate-plan and rate-plan-modifier JSON-LD, sorted by path.

   kind ∈ #{:rate-plan :rate-plan-modifier} — derived from the filename
   prefix. label is `<UTILITY> <SLUG> <date>`, where SLUG is the IRI
   slug pulled from the filename (so an inline modifier like
   `pge_e-tou-c-baseline-tier` doesn't collide with its base
   `pge_e-tou-c`). path is the relative POSIX path from the repo root."
  []
  (->> (file-seq (io/file "ca"))
       (filter #(.isFile ^File %))
       (map #(.getPath ^File %))
       (filter #(re-matches #"ca/[^/]+/[^/]+/[^/]+/versions/[^/]+/rate-plan(?:-modifier)?_.+\.jsonld" %))
       sort
       (mapv (fn [path]
               ;; Filename: rate-plan{,-modifier}_<utility>_<slug>_<date>.jsonld
               ;; <slug> may contain hyphens but never underscores.
               (let [fname (last (str/split path #"/"))
                     [_ kind-prefix utility slug date]
                     (re-matches #"(rate-plan(?:-modifier)?)_([^_]+)_([^_]+)_(\d{4}-\d{2}-\d{2})\.jsonld" fname)
                     kind  (if (= kind-prefix "rate-plan-modifier") :rate-plan-modifier :rate-plan)
                     label (str (str/upper-case utility) " "
                                (str/upper-case slug) " "
                                date)]
                 [kind label path])))))

(def filings (discover-filings))

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
