;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: CDLA-Permissive-2.0
(ns check-nbt-export
  "Every NBT export ledger resolves to exactly the one Price the tariff names,
   at every instant of a year, for every vintage.

   WHY THIS EXISTS. The NBT filings price the Energy Export Credit hour by hour,
   month by month, weekday against weekend, per interconnection vintage: 4,608
   to 5,760 mutually exclusive Prices per filing, of which one applies at any
   instant. A gap in the modifier's brackets contributes no Price at that
   instant (URPX-zoq) and does not throw, and the marginal-rate baseline cannot
   see it, because export ledgers are excluded from the import marginal; here
   it is zero tiers where one is expected. A mistyped :profile-alternatives
   container key refuses (URPX-ljo), and here that is a refused segment.

   WHAT IS CHECKED. Each NBT modifier is composed with the latest filing of
   every base plan its urpx:applicableToRatePlan names. For each vintage
   alternative the modifier declares, urpx.schedule/price-segments walks twelve
   months from the first month boundary on or after the later of the two
   filings' dates. For every segment and every ledger on a urpx:reverse
   MetricInput it asserts: no :urpx.interval/refused; the ledger appears once;
   :urpx.resolved/flow-direction is urpx:reverse; no
   :urpx.resolved/unselected-alternatives; exactly one tier; no
   :urpx.resolved/condition-gated unless declared below; and the tier's
   :urpx.resolved/price-id is the expected Price at BOTH ends of the segment.
   Segments must tile the window.

   THE EXPECTED PRICE IS COMPUTED WITHOUT THE TOU STRUCTURE. Month, hour and
   weekday-or-weekend come from the instant through java.time, and the Price
   for that cell is found by its @id, which names the cell
   (`...-m07-h17-weekday`), within the PriceSetAlternative for the vintage.
   Periods, brackets and Seasons are never read here, so a defect in them shows
   up as a disagreement rather than being reproduced on both sides. A ledger
   whose alternative holds one Price with no cell in its @id (ACC Plus) expects
   that Price at every instant.

   ABSENCES ARE DECLARED, NOT INFERRED. Where the source has no value, the
   check expects zero tiers and needs a named reason in `expected-absences`.
   An absence with no declaration fails, and so does a declaration the corpus
   no longer bears out.

   HOLIDAYS. Each tariff prices weekday against weekend/holiday, so a weekday
   holiday expects that hour's weekend cell. Which days are holidays comes from
   the calendar a composed resolution reads for the modifier: its own
   urpx:HolidayCalendar when it carries one (pge:nbt), else the base plan's
   (sce:nbt, sdge:nbt), through urpx.holidays/derive-predicate. So that a
   calendar regression cannot agree with itself, the 2026 holidays that calendar
   yields must equal `tariff-holidays-2026`, copied from the tariff text.

   Exit: 0 clean, 1 a violation, 3 refused (a declared filing missing, an
   undeclared NBT-shaped filing, no base filing, or nothing checked).

   Usage:
     clojure -M:nbt-export
     clojure -M:nbt-export --substitute <corpus path> <file>
       resolve <file> in place of the corpus filing at <corpus path>; for
       negative tests against a deliberately broken copy."
  (:require [clojure.data.json :as json]
            [clojure.string :as str]
            [urpx.coerce :as coerce]
            [urpx.core :as core]
            [urpx.holidays :as holidays]
            [urpx.index :as index]
            [urpx.schedule :as schedule]
            [urpx-rate-plans :as layout])
  (:import [java.time DayOfWeek Duration Instant LocalDate ZoneId ZonedDateTime]))

(def la (ZoneId/of "America/Los_Angeles"))

;; ---------------------------------------------------------------------------
;; Declarations
;; ---------------------------------------------------------------------------

(def nbt-filings
  "The filings this check owns. Discovery below refuses if the corpus holds an
   NBT-shaped modifier that is not listed, so a new one cannot go unchecked."
  #{"us/ca/pge/electricity/nbt/versions/2025-10-17/rate-plan-modifier_pge_nbt_2025-10-17.jsonld"
    "us/ca/sce/electricity/nbt/versions/2025-04-23/rate-plan-modifier_sce_nbt_2025-04-23.jsonld"
    "us/ca/sdge/electricity/nbt/versions/2025-01-27/rate-plan-modifier_sdge_nbt_2025-01-27.jsonld"})

(def ^:private all-months (set (range 1 13)))

(def ^:private acc-plus-2025-only
  "ACC Plus is modeled for the 2025 interconnection vintage only; the other rows of the tariff's ACC Plus table are an open deferral in tariff.toml [modeling].")

(def expected-absences
  "Where a vintage legitimately prices nothing on an export ledger, with why.
   Each row is {:alternative :ledgers :months :reason}."
  [{:alternative "sce:nbt-2025-04-23-pa-vintage-nbt26"
    :ledgers #{"sce:nbt-ledger-export-rate-generation" "sce:nbt-ledger-export-rate-delivery"}
    :months (set (range 6 13))
    :reason "source gap: SCE publishes no EEC numbers in the tariff, every cell came from CEC MIDAS, and MIDAS had not published the 2026 vintage past May at extraction (tariff.toml [modeling], first deferral)"}
   {:alternative "pge:nbt-2025-10-17-pa-vintage-2023"
    :ledgers #{"pge:nbt-ledger-acc-plus-residential" "pge:nbt-ledger-acc-plus-low-income"}
    :months all-months :reason acc-plus-2025-only}
   {:alternative "pge:nbt-2025-10-17-pa-vintage-2024"
    :ledgers #{"pge:nbt-ledger-acc-plus-residential" "pge:nbt-ledger-acc-plus-low-income"}
    :months all-months :reason acc-plus-2025-only}
   {:alternative "pge:nbt-2025-10-17-pa-vintage-2026"
    :ledgers #{"pge:nbt-ledger-acc-plus-residential" "pge:nbt-ledger-acc-plus-low-income"}
    :months all-months :reason acc-plus-2025-only}
   {:alternative "sce:nbt-2025-04-23-pa-vintage-nbt23"
    :ledgers #{"sce:nbt-ledger-acc-plus-non-equity" "sce:nbt-ledger-acc-plus-equity"}
    :months all-months :reason acc-plus-2025-only}
   {:alternative "sce:nbt-2025-04-23-pa-vintage-nbt24"
    :ledgers #{"sce:nbt-ledger-acc-plus-non-equity" "sce:nbt-ledger-acc-plus-equity"}
    :months all-months :reason acc-plus-2025-only}
   {:alternative "sce:nbt-2025-04-23-pa-vintage-nbt26"
    :ledgers #{"sce:nbt-ledger-acc-plus-non-equity" "sce:nbt-ledger-acc-plus-equity"}
    :months all-months :reason acc-plus-2025-only}
   {:alternative "sce:nbt-2025-04-23-pa-vintage-non-vintaged"
    :ledgers #{"sce:nbt-ledger-acc-plus-non-equity" "sce:nbt-ledger-acc-plus-equity"}
    :months all-months :reason acc-plus-2025-only}
   {:alternative :all-of :all-of "sdge:nbt-2025-01-27-pa-vintage"
    :ledgers #{"sdge:nbt-ledger-acc-plus-residential" "sdge:nbt-ledger-acc-plus-low-income"}
    :months all-months
    :reason "source gap: no ACC Plus rate appears on any sheet of the SDG&E schedule (tariff.toml [modeling]); the two ledgers are structure only"}])

(def tariff-holidays-2026
  "The 2026 holidays of each plan whose calendar an NBT modifier reads, from the
   tariff text rather than the calendar. nil: no calendar, so no day is a holiday."
  {;; SCE Schedule TOU-D Sheet 13, Special Condition 1: New Year's Day
   ;; (January 1), Presidents' Day (third Monday in February), Memorial Day
   ;; (last Monday in May), Independence Day (July 4), Labor Day (first Monday
   ;; in September), Veterans Day (November 11), Thanksgiving Day (fourth
   ;; Thursday in November), Christmas (December 25).
   "sce:tou-d-prime" #{"2026-01-01" "2026-02-16" "2026-05-25" "2026-07-04"
                       "2026-09-07" "2026-11-11" "2026-11-26" "2026-12-25"}
   ;; SDG&E Electric Rule 1 (Definitions), Sheet 6, which EV-TOU-5 Special
   ;; Condition 4 points to: the same eight holidays. SDG&E's NBT export-rate
   ;; CSVs mark these 2026 dates DayStart 8 (Holiday).
   "sdge:ev-tou-5"   #{"2026-01-01" "2026-02-16" "2026-05-25" "2026-07-04"
                       "2026-09-07" "2026-11-11" "2026-11-26" "2026-12-25"}
   ;; pge:nbt's own calendar. Schedule NBT names no holidays; PG&E's TOU
   ;; schedules (E-TOU-D, E-19, E-20, A-10, EV, S) each define them as New
   ;; Year's Day, President's Day, Memorial Day, Independence Day, Labor Day,
   ;; Veterans Day, Thanksgiving Day, and Christmas Day: "The dates will be
   ;; those on which the holidays are legally observed." That is California
   ;; Government Code 6701, which moves no Saturday holiday but November 11, so
   ;; Saturday July 4, 2026 stays on the Saturday and Friday July 3 is an
   ;; ordinary weekday.
   "pge:nbt"         #{"2026-01-01" "2026-02-16" "2026-05-25" "2026-07-04"
                       "2026-09-07" "2026-11-11" "2026-11-26" "2026-12-25"}})

(defn- calendar-violations
  "The derived 2026 holidays of `plan-iri`'s calendar against `tariff-holidays-2026`."
  [plan-iri pred]
  (let [want (get tariff-holidays-2026 plan-iri ::undeclared)
        days (take-while #(= 2026 (.getYear ^LocalDate %))
                         (iterate #(.plusDays ^LocalDate % 1) (LocalDate/parse "2026-01-01")))
        got  (when pred (set (map str (filter pred days))))]
    (cond (= want ::undeclared) [(str plan-iri ": no entry in tariff-holidays-2026")]
          (not= want got)       [(str plan-iri ": calendar yields 2026 holidays " (sort got)
                                      ", tariff text gives " (sort want))])))

(def expected-condition-gated
  "Ledgers whose one Price keeps a customer-class ConditionExpression clj-urpx
   cannot evaluate, so the tier is admitted and tagged."
  {"pge:nbt-ledger-acc-plus-low-income" "Low Income NBT Eligible is a customer attribute"
   "sce:nbt-ledger-acc-plus-equity"     "SCE NBT Equity Customer is a customer attribute"})

;; ---------------------------------------------------------------------------
;; Raw JSON-LD: the expectation side, read without clj-urpx
;; ---------------------------------------------------------------------------

(defn- nodes [x]
  (cond (map? x) (cons x (mapcat nodes (vals (dissoc x "@context"))))
        (sequential? x) (mapcat nodes x)
        :else nil))

(defn- as-vec [x] (cond (nil? x) [] (sequential? x) (vec x) :else [x]))

(defn- typed [doc t] (filter #(= t (get % "@type")) (nodes doc)))

(defn- ref-id [x] (get x "@id"))

(def ^:private cell-re #"-m(\d\d)-h(\d\d)-(weekday|weekend)$")

(defn- expectations
  "{:alternatives {alt-id {ledger {:grid {[m dt h] price-id} :flat price-id}}}
    :container pa-id :export-ledgers #{..} :applicable [base-iri ..]}"
  [path raw]
  (let [pds      (into {} (map (juxt #(get % "@id") #(ref-id (get % "urpx:referencesLedger"))))
                       (typed raw "urpx:PriceDefinition"))
        reverse? (set (keep #(when (= "urpx:reverse" (get-in % ["urpx:hasMetricSpecification" "urpx:flowDirection" "@id"]))
                               (get % "@id"))
                            (typed raw "urpx:MetricInput")))
        ledgers  (set (keep #(when (reverse? (ref-id (get % "urpx:referencesMetricInput"))) (get % "@id"))
                            (typed raw "urpx:Ledger")))
        pas      (typed raw "urpx:ProfileAlternatives")
        psas     (typed raw "urpx:PriceSetAlternatives")
        version  (first (typed raw "urpx:RatePlanModifierVersion"))]
    (when (not= 1 (count pas))
      (throw (ex-info (str path ": expected one urpx:ProfileAlternatives, found " (count pas)) {:refuse true})))
    (let [pa-id (get (first pas) "@id")
          alts  (into {}
                      (for [c psas
                            :when (= pa-id (ref-id (get c "urpx:referencesProfileAlternatives")))
                            psa (as-vec (get c "urpx:hasPriceSetAlternative"))]
                        [(ref-id (get psa "urpx:referencesProfileAlternative"))
                         (reduce (fn [acc p]
                                   (let [lid (pds (ref-id (get p "urpx:referencesPriceDefinition")))
                                         pid (get p "@id")]
                                     (if-let [[_ m h dt] (re-find cell-re pid)]
                                       (let [k [(parse-long m) dt (parse-long h)]]
                                         (when (get-in acc [lid :grid k])
                                           (throw (ex-info (str pid " repeats cell " k) {})))
                                         (assoc-in acc [lid :grid k] pid))
                                       (do (when (get-in acc [lid :flat])
                                             (throw (ex-info (str lid " holds two flat Prices in " (get psa "@id")) {})))
                                           (assoc-in acc [lid :flat] pid)))))
                                 {} (as-vec (get psa "urpx:hasPrice")))]))]
      (when (empty? ledgers)
        (throw (ex-info (str path ": no ledger on a urpx:reverse MetricInput") {:refuse true})))
      (when (not= (set (keep ref-id (as-vec (get (first pas) "urpx:hasProfileAlternative")))) (set (keys alts)))
        (throw (ex-info (str path ": the PriceSetAlternatives do not cover the declared alternatives") {})))
      {:container      pa-id
       :alternatives   alts
       :export-ledgers ledgers
       :version-id     (get version "@id")
       :applicable     (mapv ref-id (as-vec (get version "urpx:applicableToRatePlan")))})))

(defn- nbt-shaped?
  "A modifier whose export-ledger Prices sit under PriceSetAlternatives and
   carry touPeriodNumber: the shape this check exists for."
  [raw]
  (and (seq (typed raw "urpx:PriceSetAlternatives"))
       (some #(= "urpx:reverse" (get-in % ["urpx:hasMetricSpecification" "urpx:flowDirection" "@id"]))
             (typed raw "urpx:MetricInput"))
       (some #(contains? % "urpx:touPeriodNumber") (typed raw "urpx:Price"))))

(defn- absence-reason [exp alt lid month]
  (some (fn [{:keys [alternative all-of ledgers months reason]}]
          (when (and (or (= alternative alt)
                         (and (= alternative :all-of) (str/starts-with? alt (str all-of "-"))))
                     (ledgers lid) (months month))
            reason))
        expected-absences))

(defn- stale-declarations
  "Declared absences the corpus contradicts: the declared cell has a Price."
  [{:keys [alternatives]} file-alts]
  (for [{:keys [alternative all-of ledgers months reason]} expected-absences
        alt (if (= alternative :all-of)
              (filter #(str/starts-with? % (str all-of "-")) file-alts)
              (filter #{alternative} file-alts))
        lid ledgers
        m months
        :let [{:keys [grid flat]} (get-in alternatives [alt lid])]
        :when (or flat (some (fn [[[mm] _]] (= mm m)) grid))]
    (str alt " " lid " month " m ": declared absent (" reason ") but priced")))

(defn- weekend-day? [^ZonedDateTime z]
  (boolean (#{DayOfWeek/SATURDAY DayOfWeek/SUNDAY} (.getDayOfWeek z))))

(defn- weekday-holiday? [holiday? ^ZonedDateTime z]
  (boolean (and holiday? (not (weekend-day? z)) (holiday? (.toLocalDate z)))))

(defn- expected-id
  "[price-id nil] or [nil reason], or [nil nil] for an undeclared hole. A
   weekday holiday takes the weekend cell."
  [exp alt lid ^ZonedDateTime z]
  (let [{:keys [grid flat]} (get-in exp [:alternatives alt lid])
        m  (.getMonthValue z)
        dt (if (or (weekend-day? z) (weekday-holiday? (:holiday? exp) z)) "weekend" "weekday")
        id (cond flat flat
                 grid (get grid [m dt (.getHour z)]))]
    (if id [id nil] [nil (absence-reason exp alt lid m)])))

;; ---------------------------------------------------------------------------
;; Corpus
;; ---------------------------------------------------------------------------

(defn- latest-base-file [base-iri]
  (let [[u slug] (str/split base-iri #":" 2)
        re (re-pattern (str ".*/rate-plan_" u "_" slug "_(\\d{4}-\\d{2}-\\d{2})\\.jsonld$"))]
    (->> (layout/paths "." ["rate-plan"])
         (keep #(when-let [[_ d] (re-matches re %)] [d %]))
         sort last)))

(defn- file-date [path] (second (re-find #"_(\d{4}-\d{2}-\d{2})\.jsonld$" path)))

(defn- window
  "Twelve months from the first month boundary on or after `date`."
  [^String date]
  (let [d (LocalDate/parse date)
        s (if (= 1 (.getDayOfMonth d)) d (.plusMonths (.withDayOfMonth d 1) 1))
        start (.atStartOfDay s la)]
    [start (.plusMonths start 12)]))

;; ---------------------------------------------------------------------------
;; The walk
;; ---------------------------------------------------------------------------

(defn- check-ledger
  "Violations for one export ledger in one segment."
  [exp alt lid seg]
  (let [r   (:urpx.interval/resolved seg)
        b   ^ZonedDateTime (:tick/beginning seg)
        e   (.minus ^ZonedDateTime (:tick/end seg) (Duration/ofNanos 1))
        ls  (filter #(= lid (:urpx.resolved/ledger-id %)) (:urpx.resolved/ledgers r))
        l   (first ls)
        ts  (:urpx.resolved/tiers l)
        [want why] (expected-id exp alt lid b)
        [want-end] (expected-id exp alt lid e)
        v   (fn [msg] (str b " " lid ": " msg))]
    (cond-> []
      (> (count ls) 1) (conj (v (str "ledger appears " (count ls) " times")))
      (and l (not= "urpx:reverse" (get-in l [:urpx.resolved/flow-direction :jsonld/id])))
      (conj (v (str "flow-direction " (pr-str (:urpx.resolved/flow-direction l)))))
      (seq (:urpx.resolved/unselected-alternatives l))
      (conj (v (str "unselected-alternatives " (vec (:urpx.resolved/unselected-alternatives l)))))
      (not= want want-end)
      (conj (v (str "segment to " (:tick/end seg) " spans two cells, " want " and " want-end)))
      (and (nil? want) (nil? why))
      (conj (v (str "no Price for this cell and no declared absence; " (count ts) " tier(s) resolved")))
      (and (nil? want) why (seq ts))
      (conj (v (str "declared absent but " (count ts) " tier(s) resolved, e.g. " (:urpx.resolved/price-id (first ts)))))
      (and want (not= 1 (count ls))) (conj (v "ledger missing from the resolution"))
      (and want l (not= 1 (count ts)))
      (conj (v (str (count ts) " tiers, expected 1 (" want "); e.g. "
                    (vec (take 3 (map :urpx.resolved/price-id ts))))))
      (and want (= 1 (count ts)) (not= want (:urpx.resolved/price-id (first ts))))
      (conj (v (str "price " (:urpx.resolved/price-id (first ts)) ", expected " want)))
      (and want (= 1 (count ts))
           (not= (boolean (expected-condition-gated lid))
                 (boolean (seq (:urpx.resolved/condition-gated (first ts))))))
      (conj (v (str "condition-gated " (boolean (seq (:urpx.resolved/condition-gated (first ts))))
                    ", expected " (boolean (expected-condition-gated lid))))))))

(defn- walk-vintage
  [exp base modifier by-id alt [start end]]
  (let [segs (schedule/price-segments base [modifier] (.toInstant ^ZonedDateTime start)
                                      (.toInstant ^ZonedDateTime end) la
                                      {:profile-alternatives {(:container exp) alt}
                                       :by-id by-id})
        tiling (keep (fn [[a b]] (when (not= (.toInstant ^ZonedDateTime (:tick/end a))
                                             (.toInstant ^ZonedDateTime (:tick/beginning b)))
                                   (str "gap or overlap at " (:tick/end a))))
                     (partition 2 1 segs))
        ends (cond-> []
               (empty? segs) (conj "no segments")
               (and (seq segs) (not= (.toInstant ^ZonedDateTime start) (.toInstant ^ZonedDateTime (:tick/beginning (first segs)))))
               (conj "first segment does not start the window")
               (and (seq segs) (not= (.toInstant ^ZonedDateTime end) (.toInstant ^ZonedDateTime (:tick/end (last segs)))))
               (conj "last segment does not end the window"))
        per-seg (mapcat (fn [seg]
                          (if-let [ref (:urpx.interval/refused seg)]
                            [(str (:tick/beginning seg) " refused: " (or (:reason ref) (:message ref)))]
                            (mapcat #(check-ledger exp alt % seg) (sort (:export-ledgers exp)))))
                        segs)
        absent (frequencies (for [seg segs lid (:export-ledgers exp)
                                  :let [[want why] (expected-id exp alt lid (:tick/beginning seg))]
                                  :when (and (nil? want) why)]
                              why))]
    {:segments (count segs) :violations (vec (concat ends tiling per-seg)) :absent absent
     :holiday-segments (count (filter #(weekday-holiday? (:holiday? exp) (:tick/beginning %)) segs))
     :holiday-dates (set (keep #(when (weekday-holiday? (:holiday? exp) (:tick/beginning %))
                                  (str (.toLocalDate ^ZonedDateTime (:tick/beginning %))))
                               segs))}))

(defn -main [& args]
  (let [subst (loop [m {} [a & more] args]
                (cond (nil? a) m
                      (= a "--substitute") (recur (assoc m (first more) (second more)) (drop 2 more))
                      :else (do (println "unknown argument" a) (System/exit 3))))
        modifiers (layout/paths "." ["rate-plan-modifier"])
        raw-of (fn [p] (json/read-str (slurp (get subst p p))))
        shaped (set (filter #(nbt-shaped? (raw-of %)) modifiers))
        refuse (fn [msg] (println "REFUSED:" msg) (System/exit 3))]
    (when-let [missing (seq (remove (set modifiers) nbt-filings))]
      (refuse (str "declared NBT filings are not in the corpus: " (vec missing))))
    (when-let [extra (seq (remove nbt-filings shaped))]
      (refuse (str "NBT-shaped modifiers this check does not declare: " (vec extra))))
    (let [results
          (vec ;; the tasks, built serially: loading is cheap and refusals exit here
           (for [path (sort nbt-filings)
                 :let [raw (raw-of path)
                       exp (try (expectations path raw)
                                (catch clojure.lang.ExceptionInfo e
                                  (if (:refuse (ex-data e)) (refuse (.getMessage e)) (throw e))))
                       stale (stale-declarations exp (keys (:alternatives exp)))
                       modifier (-> (get subst path path) core/load-rate-plan-modifier
                                    coerce/coerce-rate-plan-modifier)]
                 base-iri (:applicable exp)
                 :let [[bdate bpath] (or (latest-base-file base-iri)
                                         (refuse (str path ": no base filing for " base-iri)))
                       base  (-> (get subst bpath bpath) core/load-rate-plan coerce/coerce-rate-plan)
                       mpred (holidays/derive-predicate modifier)
                       [hsrc hpred] (if mpred
                                      [(:jsonld/id modifier) mpred]
                                      [base-iri (holidays/derive-predicate base)])
                       exp   (assoc exp :holiday? hpred)
                       cal   (calendar-violations hsrc hpred)
                       by-id (reduce merge (map index/build-index [base modifier]))
                       win   (window (let [md (file-date path)] (if (pos? (compare bdate md)) bdate md)))]
                 alt (sort (keys (:alternatives exp)))]
             {:exp exp :base base :modifier modifier :by-id by-id :alt alt :window win
              :stale stale :calendar cal :holiday-source hsrc
              :label (str (:version-id exp) " + " base-iri " " bdate)}))
          ;; Each walk is independent and single-threaded, so they run in parallel.
          results
          (vec (pmap (fn [{:keys [exp base modifier by-id alt window] :as task}]
                       (let [t0 (System/nanoTime)
                             r  (walk-vintage exp base modifier by-id alt window)]
                         (merge (select-keys task [:label :alt :window :stale :calendar :holiday-source]) r
                                {:ms (quot (- (System/nanoTime) t0) 1000000)})))
                     results))]
      (doseq [{:keys [label alt window segments violations absent ms holiday-segments holiday-dates holiday-source]} results]
        (println (format "%-48s %-44s %s..%s  %5d segments  %4d on %d weekday holidays (%s)  %d violations  %.1fs"
                         label alt (.toLocalDate ^ZonedDateTime (first window))
                         (.toLocalDate ^ZonedDateTime (second window))
                         segments holiday-segments (count holiday-dates) holiday-source
                         (count violations) (/ ms 1000.0)))
        (doseq [[why n] absent]
          (println (format "    %d ledger-segment(s) expected empty: %s" n why)))
        (doseq [v (take 5 violations)] (println "    ✗" v))
        (when (> (count violations) 5) (println "    ..." (- (count violations) 5) "more")))
      (let [stale (distinct (mapcat :stale results))
            cal   (distinct (mapcat :calendar results))
            total (reduce + (map :segments results))
            bad   (reduce + (map (comp count :violations) results))
            hsegs (reduce + (map :holiday-segments results))]
        (doseq [s stale] (println "  ✗ stale declaration:" s))
        (doseq [c cal] (println "  ✗ holiday calendar:" c))
        (when (zero? total) (refuse "no segment was checked"))
        (println (format "NBT export cells: %d compositions x vintages, %d segments (%d on weekday holidays), %d violation(s), %d stale declaration(s), %d calendar disagreement(s)"
                         (count results) total hsegs bad (count stale) (count cal)))
        (System/exit (if (and (zero? bad) (empty? stale) (empty? cal)) 0 1))))))
