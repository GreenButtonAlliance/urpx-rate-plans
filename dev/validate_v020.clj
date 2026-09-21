(ns validate-v020
  "End-to-end validation of every URPX v0.2.0 filing in the corpus.

   Pyshacl confirms each JSON-LD file is SHACL-conformant. This script
   exercises the consumer path: load → coerce (Malli) → validate →
   resolve a representative price for a known instant. Catches semantic
   bugs that SHACL alone cannot see — for example, that
   PriceDefinition.referencesLedger is wired to the right Ledger, that
   per-customer credits are excluded from a $/kWh marginal sum, and that
   PriceDefinition.hasApplicabilityRule.month gates resolution by month.

   Modifier filings additionally exercise composition: for each base IRI
   in the modifier's urpx:applicableToRatePlan, the latest base filing
   in the corpus is paired with the modifier via
   urpx.price/resolve-prices-with-modifiers (clj-urpx 36a1095)
   and reports any composition failure."
  (:require [clojure.edn :as edn]
            [clojure.java.io :as io]
            [clojure.string :as str]
            [urpx.core :as core]
            [urpx.coerce :as coerce]
            [urpx.price :as price]
            [urpx.schema :as schema])
  (:import [java.io File]
           [java.time ZoneId ZonedDateTime]))

(defn discover-filings
  "Walk the us/ corpus and return [[kind label path] ...] for every
   rate-plan and rate-plan-modifier JSON-LD, sorted by path.

   kind ∈ #{:rate-plan :rate-plan-modifier} — derived from the filename
   prefix. label is `<UTILITY> <SLUG> <date>`, where SLUG is the IRI
   slug pulled from the filename (so an inline modifier like
   `pge_e-tou-c-baseline-tier` doesn't collide with its base
   `pge_e-tou-c`). path is the relative POSIX path from the repo root."
  []
  (->> (file-seq (io/file "us"))
       (filter #(.isFile ^File %))
       (map #(.getPath ^File %))
       ;; Depth-independent: matches on the versions/<date>/ segment rather than
       ;; on a fixed prefix depth, so a restructure does not silently match zero.
       (filter #(re-matches #"us/.*/versions/[^/]+/rate-plan(?:-modifier)?_.+\.jsonld" %))
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

;; A refusal is not a failure when the refusal IS the right answer. Both of
;; these mean "nothing here is priced per kWh at this instant", and clj-urpx
;; refuses rather than returning 0, which would read as free:
;;
;;   :no-energy-ledger         nothing resolved carries a summable
;;                             measurementKind. CPAU E-14 and E-16 price only
;;                             per-lamp, per-fixture and per-month charges.
;;   :all-energy-tiers-excluded  an energy ledger resolved but every tier in it
;;                             is event-driven (urpx:hasDynamicPricing) or
;;                             recurring, so there is no non-event rate to
;;                             report. CPAU E-14 composed with E-HRA is this:
;;                             the only per-kWh thing in the composition is a
;;                             hydroelectric adjustment that applies under
;;                             generation conditions, not continuously.
;;
;; Accepting these is safe in the direction that matters: a refusal can never be
;; mistaken for a price, which is the failure this gate exists to catch. What it
;; would hide is a regression where EVERYTHING starts refusing, so -main refuses
;; outright if no filing produces a marginal rate at all.
(def legitimate-refusals #{:no-energy-ledger :all-energy-tiers-excluded})

(def refusal-tally (atom {}))
(def marginal-count (atom 0))

(defn- note-refusal! [reason] (swap! refusal-tally update reason (fnil inc 0)))

(defn pad [s n] (let [s (str s)] (str s (apply str (repeat (max 0 (- n (count s))) " ")))))

(defn- name-width [filings] (apply max (map (comp count second) filings)))

(defn- iri->kw
  "URPX-style IRI string `\"sce:care\"` → namespaced keyword `:sce/care`."
  [iri]
  (let [[ns local] (str/split iri #":" 2)]
    (keyword ns local)))

(defn- kw->iri
  "Inverse of iri->kw."
  [kw]
  (str (namespace kw) ":" (name kw)))

(defn- read-pairings
  "Load reports/modifier-base-pairings.edn (auto-generated by
   dev/list_modifier_base_pairings.py)."
  []
  (-> "reports/modifier-base-pairings.edn"
      slurp
      edn/read-string))

(defn- build-base-iri-lookup
  "{base-iri-keyword → {:path <jsonld path> :date <YYYY-MM-DD>}} keyed on the
   IRI built from the filename's <utility>_<slug>. When multiple versions of
   the same base exist, the most recent date wins."
  [filings]
  (reduce
   (fn [acc [kind _ path]]
     (if-not (= kind :rate-plan)
       acc
       (let [fname (last (str/split path #"/"))
             [_ utility slug date]
             (re-matches #"rate-plan_([^_]+)_([^_]+)_(\d{4}-\d{2}-\d{2})\.jsonld" fname)]
         (if-not date
           acc
           (let [iri-kw   (keyword utility slug)
                 existing (get acc iri-kw)]
             (if (or (nil? existing) (pos? (compare date (:date existing))))
               (assoc acc iri-kw {:path path :date date})
               acc))))))
   {}
   filings))

(defn- validate-rate-plan [path]
  (let [raw (core/load-rate-plan path)
        plan (coerce/coerce-rate-plan raw)]
    (if (coerce/validate schema/RatePlan plan)
      (do
        (print "load+coerce ✓ ")
        (flush)
        ;; See `legitimate-refusals`: a refusal with one of those reasons is the
        ;; right answer, not a failure. Any other refusal still fails.
        (let [ok (try
                   (let [resolved (price/resolve-prices plan probe-instant)
                         ledger-count (count (:urpx.resolved/ledgers resolved))
                         marginal (price/marginal-unit-rate resolved)]
                     (swap! marginal-count inc)
                     (print (format "resolve ✓  (%d ledgers, marginal=%s)"
                                    ledger-count marginal))
                     true)
                   (catch Exception e
                     (let [reason (:reason (ex-data e))]
                       (if (legitimate-refusals reason)
                         (do (note-refusal! reason)
                             (print (format "resolve ✓  (%s; nothing priced per kWh here)"
                                            (name reason)))
                             true)
                         (do (print (format "resolve ✗  %s" (.getMessage e)))
                             false)))))]
          (println)
          ok))
      (do
        (println "validate ✗")
        (let [explanation (coerce/explain schema/RatePlan plan)]
          (println "    explain:" (pr-str explanation)))
        false))))

(defn- compose-modifier-with-base
  "Compose `modifier` into the latest version of `base-kw`'s base RatePlan
   filing. Returns a map: :status ∈ #{:ok :refused :no-corpus-base :error},
   plus :ledgers + :marginal on :ok, or :reason on :refused, or :error.

   :refused is a PASS. A composition can legitimately price nothing per kWh:
   CPAU E-14 is street lighting, and composing the hydroelectric adjustment
   onto it contributes one energy ledger whose every tier is event-driven. See
   `legitimate-refusals` for why accepting these does not make the gate
   vacuous."
  [modifier base-kw base-iri-lookup]
  (if-let [base-info (get base-iri-lookup base-kw)]
    (let [base (-> (:path base-info) core/load-rate-plan coerce/coerce-rate-plan)]
      (try
        (let [resolved (price/resolve-prices-with-modifiers base [modifier] probe-instant)
              marginal (price/marginal-unit-rate resolved)]
          (swap! marginal-count inc)
          {:status   :ok
           :ledgers  (count (:urpx.resolved/ledgers resolved))
           :marginal marginal})
        (catch Exception e
          (let [reason (:reason (ex-data e))]
            (if (legitimate-refusals reason)
              (do (note-refusal! reason)
                  {:status :refused :reason reason})
              {:status :error :error (.getMessage e)})))))
    {:status :no-corpus-base}))

(defn- validate-rate-plan-modifier [path pairings base-iri-lookup]
  (let [raw      (core/load-rate-plan-modifier path)
        modifier (coerce/coerce-rate-plan-modifier raw)]
    (if-not (coerce/validate schema/RatePlanModifier modifier)
      (do (println "validate ✗")
          (let [explanation (coerce/explain schema/RatePlanModifier modifier)]
            (println "    explain:" (pr-str explanation)))
          false)
      (let [mod-iri  (:jsonld/id modifier)
            mod-kw   (iri->kw mod-iri)
            base-kws (get-in pairings [:by-modifier mod-kw :applicable-to])]
        (print "load+coerce ✓  ")
        (flush)
        (cond
          (empty? base-kws)
          (do (println "(no applicable bases declared)") true)

          :else
          (let [results  (mapv #(assoc (compose-modifier-with-base modifier % base-iri-lookup)
                                       :base %)
                               base-kws)
                ok       (filterv #(= :ok (:status %)) results)
                refused  (filterv #(= :refused (:status %)) results)
                failures (filterv #(not (#{:ok :refused} (:status %))) results)
                total    (count results)]
            (if (empty? failures)
              (do
                (println (format "compose ✓ × %d (%s%s)"
                                 total
                                 (if (seq ok)
                                   (format "e.g. %s → %d ledgers, marginal=%s"
                                           (kw->iri (:base (first ok)))
                                           (:ledgers (first ok))
                                           (:marginal (first ok)))
                                   "no base prices anything per kWh")
                                 (if (seq refused)
                                   (format "; %d priced nothing per kWh" (count refused))
                                   "")))
                true)
              (do
                (println (format "compose %d/%d" (count ok) total))
                (doseq [f failures]
                  (let [reason (case (:status f)
                                 :no-corpus-base "no base filing in corpus"
                                 :error          (:error f)
                                 (str (:status f)))]
                    (println (format "    ✗ %s — %s" (kw->iri (:base f)) reason))))
                false))))))))

(defn validate-one [width [kind label path] pairings base-iri-lookup]
  (print (pad label width) "")
  (flush)
  (try
    (boolean
     (case kind
       :rate-plan          (validate-rate-plan path)
       :rate-plan-modifier (validate-rate-plan-modifier path pairings base-iri-lookup)))
    (catch Exception e
      (println "load+coerce ✗  " (.getMessage e))
      false)))

(defn -main [& _]
  (println "Probe instant:" probe-instant)
  (println)
  (when (empty? filings)
    (println "ERROR: corpus discovery found no filings under us/. The tree moved")
    (println "       and this script was not updated, or this is not the repo root.")
    (println "       Refusing to report 0/0 as success.")
    (System/exit 3))
  (let [w               (inc (name-width filings))
        pairings        (read-pairings)
        base-iri-lookup (build-base-iri-lookup filings)
        results         (mapv #(validate-one w % pairings base-iri-lookup) filings)
        failed          (count (remove true? results))
        total           (count results)]
    (println)
    (when (seq @refusal-tally)
      (println (format "marginal rate refused (correctly) on %d of %d checks: %s"
                       (reduce + (vals @refusal-tally))
                       (+ @marginal-count (reduce + (vals @refusal-tally)))
                       (str/join ", " (for [[r n] (sort-by key @refusal-tally)]
                                        (format "%d %s" n (name r)))))))
    ;; The one way accepting refusals could go vacuous: a change that makes
    ;; EVERYTHING refuse would otherwise report green.
    (when (zero? @marginal-count)
      (println)
      (println "REFUSED: not one filing or composition produced a marginal unit rate.")
      (println "         Every check refused, so this run proves nothing. Refusing to")
      (println "         report it as a pass.")
      (System/exit 3))
    (println (format "%d/%d passed" (- total failed) total))
    (System/exit (if (zero? failed) 0 1))))
