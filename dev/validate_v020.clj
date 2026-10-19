(ns validate-v020
  "End-to-end validation of every URPX v0.2.0 filing in the corpus.

   dev/shacl.sh confirms each JSON-LD file is SHACL-conformant. This script
   exercises the consumer path: load → coerce (Malli) → validate →
   resolve a representative price at known instants. Catches semantic
   bugs that SHACL alone cannot see — for example, that
   PriceDefinition.referencesLedger is wired to the right Ledger, that
   per-customer credits are excluded from a $/kWh marginal sum, and that
   PriceDefinition.hasApplicabilityRule.month gates resolution by month.

   Modifier filings additionally exercise composition: for each base IRI
   in the modifier's urpx:applicableToRatePlan, the latest base filing
   in the corpus is paired with the modifier via
   urpx.price/resolve-prices-with-modifiers (clj-urpx 36a1095)
   and reports any composition failure.

   Three modes:

     clojure -M:validate                    the report above, at the first probe
                                            instant. Exit 0, 1, 3.
     clojure -M:validate --check-baseline   compare every resolved marginal rate,
                                            at every probe instant, against the
                                            recorded file. Exit 0, 1 (a value
                                            moved), 2 (rows appeared or
                                            vanished), 3 (refused).
     clojure -M:validate --record-baseline  re-record that file. Deliberate and
                                            manual: nothing else invokes it.

   The report and the baseline read the same `probe-plan` and
   `compose-modifier-with-base`, so they cannot disagree about what a filing
   resolves to. The report covers one instant; the baseline covers every instant
   in `probe-instants`, and that list says why one was not enough. See the
   baseline section below for why a recorded value rather than a bound."
  (:require [clojure.edn :as edn]
            [clojure.java.io :as io]
            [clojure.string :as str]
            [urpx.core :as core]
            [urpx.coerce :as coerce]
            [urpx.index :as index]
            [urpx.price :as price]
            [urpx.schema :as schema]
            [urpx-rate-plans :as layout])
  (:import [java.time ZoneId ZonedDateTime]))

(defn discover-filings
  "Walk the us/ corpus and return [[kind label path] ...] for every
   rate-plan and rate-plan-modifier JSON-LD, sorted by path.

   kind ∈ #{:rate-plan :rate-plan-modifier} — derived from the filename
   prefix. label is `<UTILITY> <SLUG> <date>`, where SLUG is the IRI
   slug pulled from the filename (so an inline modifier like
   `pge_e-1-income-tier` doesn't collide with its base
   `pge_e-1`). path is the relative POSIX path from the repo root."
  []
  (->> (layout/paths ".")
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

(defn- at
  "A probe instant in the corpus's timezone. Minutes are always zero: every
   startTime and endTime in the corpus falls on the hour."
  [y m d h]
  (ZonedDateTime/of y m d h 0 0 0 la))

;; --- the probe instants ------------------------------------------------------
;;
;; WHY THERE IS A LIST. This file used to record one instant, summer weekday
;; 17:00, which is a gate reporting on one hour of one day type of one season.
;; Moving a TOU discriminator from Price onto PriceDefinition changed which
;; price was live at 8 of the 19 instants then derived on sdge:ev-tou, ev-tou-2
;; and ev-tou-5, and at 17 of 19 on sdge:tou-dr2. The single instant at which all
;; four were unchanged was the instant this file probed. sdge:ev-tou-5 read
;; 0.41420 at summer super-off-peak where the filing says 0.12852, a rate wrong
;; by 0.28568/kWh at most hours of most days, and every gate here was green.
;;
;; HOW THE SET WAS DERIVED, on 2026-09-21, rather than picked. The corpus was
;; resolved at all 744 instants of an hourly grid: every month of the window below, on a
;; weekday, on a weekend day, and on that month's holiday where the embedded
;; calendars have one. That grid separated the corpus into 106 distinct
;; behaviors. The 19 derived were one per (season regime x day type x band) that
;; the corpus then distinguished, and the set was then measured against the grid
;; for the two properties that make it worth running:
;;
;;   EVERY LIVE PRICE IS READ. Over the year the corpus then fed 2,617 distinct
;;   (row, price) pairs into a marginal rate. Those 19 read all 2,617. The
;;   single instant read 1,678 of them, 64%, so a third of the corpus's prices
;;   could have taken any value at all without moving a recorded number.
;;
;;   NO TWO ARE INTERCHANGEABLE. No two of those 19 recorded the same thing for
;;   every filing. Each differed from every other on at least one row, so
;;   dropping any one of them dropped a season, a day type or a band with it.
;;
;; DATE VALIDITY was checked, not assumed. The latest startDate in the corpus was
;; 2026-04-01 and no filing carried an expirationDate, so 2026-04-01 through
;; 2027-03-31 was the first full year in which every filing was in force, and
;; every instant derived then sat inside it. A winter probe in January 2026 would
;; have resolved to :no-energy-ledger on the 2026-04-01 filings and taught nothing.
;; At all 744 grid instants the corpus resolved 150 rates and 9 refusals, the same
;; 9 rows every time, so no probe derived then refused everywhere.
;;
;; SEASON REGIMES. Summer is Jun-Sep for PG&E, SCE, SMUD, LADWP and CPAU
;; E-1-TOU; Jun-Oct for SDG&E; May-Oct for CPAU E-2 through E-7. That is five
;; regimes rather than two: deep summer, deep winter (Nov-Mar, which resolve
;; alike), and three shoulder months that resolve like none of the others. April
;; and October carry the PG&E and SCE month-gated elements (urpx:month --04
;; --10) as well, which resolve an extra ledger on rows that no deep-winter
;; probe sees.
;;
;; Adding, moving or renaming an instant invalidates the rows recorded under its
;; :id, so it is a --record-baseline and a diff to review, never a quiet edit.
(def probe-instants
  "Every instant the baseline records a row at. :id is the stable key in the
   baseline file; :why is the band, season and day type the instant is there
   for. Rows are written in this order."
  [{:id "summer-weekday-peak"      :at (at 2026 7 15 17)
    :why "Wed, deep summer, on-peak in every TOU plan that has one: 16-21 for SDG&E, SCE and PG&E and CPAU, 17-20 for PG&E E-TOU-D and SCE TOU-D-5-8PM"}
   {:id "summer-weekday-shoulder"  :at (at 2026 7 15 15)
    :why "the 15-16 partial-peak hour, carved out by exactly three schedules (PG&E E-ELEC, PG&E EV2, CPAU E-1-TOU) and off-peak for the rest"}
   {:id "summer-weekday-midday"    :at (at 2026 7 15 11)
    :why "SDG&E's 10-14 weekday super-off-peak solar window; no other probe sits in it"}
   {:id "summer-weekday-overnight" :at (at 2026 7 15 2)
    :why "the SDG&E EV 00-06 weekday super-off-peak band, which is the band the discriminator defect mispriced"}
   {:id "summer-weekend-peak"      :at (at 2026 7 18 17)
    :why "Sat: the same clock hour as summer-weekday-peak, and the weekend price wherever a plan discriminates by day type"}
   {:id "summer-sunday-peak"       :at (at 2026 7 19 18)
    :why "Sun 18: Peak hours on Monday through Saturday for SCL RTC and RTS, which price Sunday Mid-Peak through urpx:daysOfWeek; no other probe falls on a Sunday"}
   {:id "summer-holiday-peak"      :at (at 2026 9 7 17)
    :why "Labor Day: the third day type. 8 rows move against the same hour on a weekday, all of them CPAU E-4-TOU, CPAU E-7-TOU, PG&E E-TOU-D or a composition over one"}
   {:id "summer-holiday-morning"   :at (at 2026 9 7 7)
    :why "Labor Day 07, inside the 06-10 band SDG&E prices Off-Peak on a weekday and Super Off-Peak on a weekend or holiday; the 17:00 holiday probes sit in On-Peak on every day type and cannot see a holiday calendar's effect on that band"}
   {:id "winter-weekday-peak"      :at (at 2026 12 8 17)
    :why "Tue, deep winter (Nov-Mar all resolve alike), on-peak"}
   {:id "winter-weekday-shoulder"  :at (at 2026 12 8 15)
    :why "the same 15-16 partial peak in winter"}
   {:id "winter-weekday-midday"    :at (at 2026 12 8 11)
    :why "winter 10-14, where SDG&E prices its super-off-peak window as off-peak"}
   {:id "winter-weekday-morning"   :at (at 2026 12 8 8)
    :why "the morning bands (SDG&E 06-10, SCE 08-16), still overnight inside CPAU E-1-TOU's 21-09"}
   {:id "winter-weekday-overnight" :at (at 2026 12 8 2)
    :why "winter super-off-peak, the band on which sdge:tou-dr2 was wrong"}
   {:id "winter-weekend-peak"      :at (at 2026 12 12 17)
    :why "Sat: day-type discrimination at the winter peak hour"}
   {:id "winter-holiday-peak"      :at (at 2026 12 25 17)
    :why "Christmas, observed on the day it falls: the holiday-aware rows again, now against a winter weekday"}
   {:id "winter-holiday-morning"   :at (at 2026 12 25 7)
    :why "Christmas 07 (a Friday): the same 06-10 weekday-versus-holiday band in winter"}
   {:id "april-weekday-peak"       :at (at 2026 4 7 17)
    :why "Tue: winter for every utility, plus the PG&E and SCE month --04 elements that no deep-winter probe resolves"}
   {:id "april-weekday-morning"    :at (at 2026 4 7 9)
    :why "09, where SDG&E's 06-10 off-peak and CPAU E-1-TOU's 09-15 meet, with the April elements live"}
   {:id "april-weekday-overnight"  :at (at 2026 4 7 2)
    :why "the April elements against the overnight band"}
   {:id "october-weekday-peak"     :at (at 2026 10 6 17)
    :why "Tue: SDG&E and CPAU E-2 through E-7 are still in summer while PG&E, SCE, SMUD, LADWP and CPAU E-1-TOU are in winter. 52 rates move against deep winter, and the month --10 elements are live"}
   {:id "october-weekday-shoulder" :at (at 2026 10 6 15)
    :why "the same split season at the 15-16 partial-peak hour"}
   {:id "may-weekday-peak"         :at (at 2026 5 5 17)
    :why "Tue: the one month where CPAU E-2 through E-7 are in summer and everything else, CPAU E-1-TOU included, is in winter"}])

;; The human report below resolves one instant rather than all of them: every
;; filing at every instant is a wall of output, and the report is for reading. The baseline
;; is the part that asserts, and it asserts at every one of them.
(def probe-instant (:at (first probe-instants)))

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

;; :outside-version-window is NOT in that set either, and is admitted only when
;; THE FILING ITSELF says so. clj-urpx puts the window it refused against into
;; ex-data as :expires, read straight off the version's urpx:expirationDateTime,
;; so a filing can only be excused here by carrying a bound that has passed.
;; There is no list to maintain and nothing to forget to remove: delete the
;; bound and the excuse disappears with it.
;;
;; A version that has not started yet is admitted the same way, from the
;; filing's own urpx:effectiveDateTime, which clj-urpx puts into ex-data as
;; :effective. It once failed here, on the reasoning that every probe instant
;; sat in the corpus's present, so a version not yet in force must be misdated.
;; That stopped holding when a filing was added whose rates genuinely change
;; inside the probe window: PSE Schedule 307 has versions effective 2026-05-01
;; and 2026-10-01, and no PSE version covers every instant from April to
;; December. Both cases record their own reason, :outside-version-window for a
;; version that has ended and :not-yet-effective for one that has not begun,
;; so the baseline still says which. A misdated filing now refuses rather than
;; fails at the instants before its date, and is caught by its own rows
;; changing on --check-baseline.
(defn- ^java.time.LocalDateTime as-local
  "A LocalDateTime from whichever java.time type clj-urpx hands back.

   :expires is a LocalDateTime today, because urpx:expirationDateTime is naive
   in every one of this corpus's datetimes. It may become a ZonedDateTime:
   the zone is available, as urpx:timezoneIdentifier on the urpx:RatePlan, and
   every urpx:RatePlan carries one. Accept either so that change lands upstream
   without this gate going quiet or throwing."
  [x]
  (cond
    (instance? java.time.LocalDateTime x) x
    (instance? java.time.ZonedDateTime x) (.toLocalDateTime ^java.time.ZonedDateTime x)
    (instance? java.time.OffsetDateTime x) (.toLocalDateTime ^java.time.OffsetDateTime x)
    :else nil))

(defn- expired-before?
  "True when ex-data names a window this instant is past the end of."
  [data ^java.time.ZonedDateTime instant]
  (let [expires (as-local (:expires data))]
    (and (= (:reason data) :outside-version-window)
         (some? expires)
         (not (.isAfter expires (.toLocalDateTime instant))))))

(defn- not-yet-effective?
  "True when ex-data names a window this instant falls before the start of."
  [data ^java.time.ZonedDateTime instant]
  (let [effective (as-local (:effective data))]
    (and (= (:reason data) :outside-version-window)
         (some? effective)
         (.isAfter effective (.toLocalDateTime instant)))))

(defn- refusal-reason
  "The reason a refusal is recorded under: :not-yet-effective for a version
   that has not begun at `instant`, otherwise clj-urpx's own reason."
  [data instant]
  (if (not-yet-effective? data instant) :not-yet-effective (:reason data)))

;; :condition-gated-tier is NOT in that set, and is admitted only for the two
;; filings named below. clj-urpx refuses rather than summing a price whose
;; urpx:ConditionExpression it cannot evaluate, and that refusal answers two
;; very different situations:
;;
;;   a MODELING DEFECT, where the gated set is mutually exclusive and the filing
;;   should have stated a selection instead. SCE CCA-CRS filed twenty PCIA
;;   vintages this way and summing them reported 0.95664 for TOU-D-PRIME against
;;   a true 0.59423 to 0.62691. Blanket-accepting the refusal would have hidden
;;   that, which is the whole reason to keep the class out of the set.
;;
;;   a GENUINE PREDICATE, where the price depends on a fact no document can
;;   carry: whether an event was called on the day being priced. Nothing models
;;   its way out of that, and refusing is the correct answer.
;;
;; So the two filings whose gates are genuine predicates are named here, with
;; the count they are expected to carry. A filing that acquires a
;; condition-gated refusal without an entry FAILS, which forces the modeling
;; defect and the genuine predicate to be told apart by a person rather than
;; absorbed by a set membership.
(def condition-gated-expected
  {"pge:e-rsmart"        {:prices 2
                          :why "SmartDay event credits. Sheet 2 footnote * confines the $0.60000 to SmartDays and footnote ** applies the credits to usage on days NOT declared SmartDays, so both sides turn on whether an event was called. Sheet 4 publishes only bounds, nine to fifteen per year, and a 4pm day-ahead notification, never dates."}
   "sce:tou-d-prime-cpp" {:prices 2
                          :why "CPP event credits, gated on whether a Critical Peak Pricing event is called that day and on a grandfathered-customer attribute. Summing them made the composed marginal negative, -0.13897 at summer peak, which says a customer is paid to consume."}})

;; A filing that states mutually exclusive alternatives cannot be resolved
;; without choosing one, and clj-urpx refuses with :unselected-alternatives
;; rather than summing them. That refusal is NOT in `legitimate-refusals` on
;; purpose. Accepting it would drop the filing out of the recorded baseline
;; entirely, which is how a gate goes quiet on exactly the filings that most
;; need watching: SCE CCA-CRS and DA-CRS each state twenty PCIA vintages, of
;; which one applies to any customer, and summing them reported 0.95664 for
;; TOU-D-PRIME against a true range of 0.59423 to 0.62691.
;;
;; So the harness NOMINATES a cell, here, in the open, and records the rate that
;; nomination produces. A filing that gains alternatives without an entry below
;; fails the gate and forces someone to decide, which is the behaviour we want:
;; there is no defensible default, and picking one silently would assert a
;; customer attribute the corpus does not know.
;;
;; The nominated vintage is the earliest SCE files, 2001. Any cell would
;; exercise the selection path equally; the earliest is chosen because it is
;; stable (SCE adds vintages forward, so a new filing does not move it) and
;; because a moving nomination would show up as a baseline diff that means
;; nothing. This records one of twenty cells: the sweep that checked all 1520
;; per-vintage cells is a one-time verification, not a per-commit gate.
(def profile-alternative-nominations
  {"sce:cca-crs-2026-03-20-pa-pcia-vintage" "sce:cca-crs-2026-03-20-pa-vintage-2001"
   "sce:da-crs-2026-03-20-pa-pcia-vintage"  "sce:da-crs-2026-03-20-pa-vintage-2001"
   "sce:cca-crs-2026-06-25-pa-pcia-vintage" "sce:cca-crs-2026-06-25-pa-vintage-2001"
   "sce:da-crs-2026-06-25-pa-pcia-vintage"  "sce:da-crs-2026-06-25-pa-vintage-2001"
   "sce:cca-crs-2026-10-01-pa-pcia-vintage" "sce:cca-crs-2026-10-01-pa-vintage-2001"
   "sce:da-crs-2026-10-01-pa-pcia-vintage"  "sce:da-crs-2026-10-01-pa-vintage-2001"
   ;; PG&E CCA-CRS crosses vintage with CARE enrollment; the earliest vintage,
   ;; not CARE, is the cell that carries a PCIA Price.
   "pge:cca-crs-2026-01-01-pa-vintage-care" "pge:cca-crs-2026-01-01-pa-v2009"
   ;; Shoreline exercises the multiplier and all five undergrounding charges.
   "scl:residential-suburban-2026-01-01-pa-jurisdiction" "scl:residential-suburban-2026-01-01-pa-shoreline"
   "scl:residential-suburban-2027-01-01-pa-jurisdiction" "scl:residential-suburban-2027-01-01-pa-shoreline"
   "scl:residential-suburban-2028-01-01-pa-jurisdiction" "scl:residential-suburban-2028-01-01-pa-shoreline"
   ;; Inside city limits carries the higher Municipal Franchise Fee rate.
   "gpc:r-2026-06-01-pa-franchise-fee-location" "gpc:r-2026-06-01-pa-inside-city-limits"
   "gpc:tou-reo-2026-06-01-pa-franchise-fee-location" "gpc:tou-reo-2026-06-01-pa-inside-city-limits"
   "gpc:tou-oa-2026-06-01-pa-franchise-fee-location" "gpc:tou-oa-2026-06-01-pa-inside-city-limits"
   "gpc:tou-rd-2026-06-01-pa-franchise-fee-location" "gpc:tou-rd-2026-06-01-pa-inside-city-limits"
   "gpc:pps-2026-06-01-pa-franchise-fee-location" "gpc:pps-2026-06-01-pa-inside-city-limits"
   ;; The business schedules cross FCR-27's voltage level with MFF-11's
   ;; location; Secondary Distribution inside city limits carries the highest
   ;; fuel and franchise fee rates.
   "gpc:gs-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:gs-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:ogs-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:ogs-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:pls-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:pls-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:plm-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:plm-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:pll-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:pll-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:sch-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:sch-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:slm-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:slm-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:g-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:g-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:fs-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:fs-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:aps-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:aps-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:sas-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:sas-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:sas-nd-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:sas-nd-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:iop-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:iop-2026-06-01-pa-secondary-inside-city-limits"
   ;; ET-23 serves at 19,800 volts or higher, never Secondary Distribution.
   "gpc:et-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:et-2026-06-01-pa-primary-inside-city-limits"
   "gpc:tou-eo-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:tou-eo-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:tou-gsd-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:tou-gsd-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:tou-hlf-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:tou-hlf-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:tou-fd-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:tou-fd-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:tou-rn-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:tou-rn-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:tou-sc-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:tou-sc-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:tou-evc-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:tou-evc-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:tc-m-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:tc-m-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:ud-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:ud-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:tou-eol-2026-06-01-pa-voltage-level-franchise-fee-location" "gpc:tou-eol-2026-06-01-pa-secondary-inside-city-limits"
   "gpc:eol-2026-06-01-pa-franchise-fee-location" "gpc:eol-2026-06-01-pa-inside-city-limits"
   "gpc:olg-2026-06-01-pa-franchise-fee-location" "gpc:olg-2026-06-01-pa-inside-city-limits"
   "gpc:olng-2026-06-01-pa-franchise-fee-location" "gpc:olng-2026-06-01-pa-inside-city-limits"
   "gpc:rlg-2026-06-01-pa-franchise-fee-location" "gpc:rlg-2026-06-01-pa-inside-city-limits"
   "gpc:tc-u-2026-06-01-pa-franchise-fee-location" "gpc:tc-u-2026-06-01-pa-inside-city-limits"
   ;; OPT-8 crosses customer kind (its DSM schedule) with the franchise fee
   ;; location; residential inside city limits, as on Schedule R.
   "gpc:opt-2026-06-01-pa-customer-kind-franchise-fee-location" "gpc:opt-2026-06-01-pa-residential-inside-city-limits"
   ;; One block, the smallest subscription Rider CS sells.
   "jemc:cs-2022-06-01-pa-solar-blocks" "jemc:cs-2022-06-01-pa-1-block"
   ;; 100 percent carries Rider GP's full $0.01/kWh premium.
   "jemc:gp-2023-01-01-pa-green-power-share" "jemc:gp-2023-01-01-pa-100-percent"
   ;; Photocell-controlled is the alternative with a per-kWh price; the
   ;; Cooperative-owned alternative prices lamps only.
   "jemc:s-2026-01-01-pa-lighting-system" "jemc:s-2026-01-01-pa-customer-owned-photocell"
   ;; Single phase, the lower Service Charge; phase moves no per-kWh price.
   "jemc:gs-2026-01-01-pa-service-phase" "jemc:gs-2026-01-01-pa-single-phase"
   "jemc:gsae-2026-01-01-pa-service-phase" "jemc:gsae-2026-01-01-pa-single-phase"
   "jemc:ts-2026-01-01-pa-service-phase" "jemc:ts-2026-01-01-pa-single-phase"
   "jemc:gstou-2026-01-01-pa-service-phase" "jemc:gstou-2026-01-01-pa-single-phase"
   "jemc:cev-2026-01-01-pa-service-phase" "jemc:cev-2026-01-01-pa-single-phase"})

(defn- nominations-for
  "The entries of `profile-alternative-nominations` whose container is in
   `docs`. clj-urpx 0.36.0 refuses a selection keyed by a container absent from
   the documents being resolved, so each call passes only its own."
  [& docs]
  (let [present (into #{} (mapcat #(keys (index/entities-of-type % "urpx:ProfileAlternatives"))) docs)]
    (select-keys profile-alternative-nominations present)))

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
  "{base-iri-keyword → [{:path <jsonld path> :date <YYYY-MM-DD>} ...]} keyed on
   the IRI built from the filename's <utility>_<slug>, every version of the
   base, oldest first. `base-at` picks one per instant."
  [filings]
  (update-vals
   (reduce
    (fn [acc [kind _ path]]
      (if-not (= kind :rate-plan)
        acc
        (let [fname (last (str/split path #"/"))
              [_ utility slug date]
              (re-matches #"rate-plan_([^_]+)_([^_]+)_(\d{4}-\d{2}-\d{2})\.jsonld" fname)]
          (if-not date
            acc
            (update acc (keyword utility slug) (fnil conj []) {:path path :date date})))))
    {}
    filings)
   #(vec (sort-by :date %))))

(defn- base-at
  "The version of a base to compose against at `instant`: the latest one whose
   date is on or before the instant's local date in the probe zone, or the
   latest of all when every version is later. Taking the latest of all at every
   instant composed scl:residential-suburban-2026-01-01 with scl:rts-2028-01-01,
   which is not yet effective at any probe instant, so every cell refused."
  [versions ^ZonedDateTime instant]
  (let [day (str (.toLocalDate (.withZoneSameInstant instant la)))]
    (or (last (filter #(not (pos? (compare (:date %) day))) versions))
        (last versions))))

;; Load, coercion and Malli validation are per FILING, not per instant, so they
;; are cached: otherwise every filing would repeat them once per instant. Measured on this corpus, validation is the expensive half by a wide
;; margin (a full corpus sweep runs in 0.03s per instant once validated, against
;; 0.6s when every instant re-validates), which is why widening the probe set
;; costs almost nothing here.
;;
;; The parsed graph is cached too, and the plan or modifier is taken from it the
;; way core/load-rate-plan and core/load-rate-plan-modifier take it, so the
;; corpus-wide reference check in `mistyped-hits` reads the same parse rather
;; than parsing every filing a second time.
(def ^:private load-graph! (memoize core/load-graph))

(defn- the-entity
  "The one entity of `type-literal` in the document at `path`, as
   core/load-rate-plan finds it: zero or several is an error."
  [path type-literal]
  (let [found (->> (load-graph! path)
                   (mapcat core/expand-document-entities)
                   (filterv #(= type-literal (:jsonld/type %))))]
    (if (= 1 (count found))
      (first found)
      (throw (ex-info (format "%d %s entities in document, expected one" (count found) type-literal)
                      {:src path :ids (mapv :jsonld/id found)})))))

(def ^:private load-plan!
  (memoize (fn [path] (-> path
                          (the-entity "urpx:RatePlan")
                          coerce/coerce-rate-plan))))

(def ^:private plan-valid?
  (memoize (fn [path] (coerce/validate schema/RatePlan (load-plan! path)))))

(def ^:private load-modifier!
  (memoize (fn [path] (-> path
                          (the-entity "urpx:RatePlanModifier")
                          coerce/coerce-rate-plan-modifier))))

(def ^:private modifier-valid?
  (memoize (fn [path] (coerce/validate schema/RatePlanModifier (load-modifier! path)))))

(defn- probe-plan
  "Resolve the base RatePlan at `path` at `instant` and return WHAT HAPPENED,
   without printing or tallying. Exactly one of:

     {:status :ok       :ledgers n :rate <BigDecimal>}
     {:status :refused  :reason <keyword>}      see `legitimate-refusals`
     {:status :error    :error <message>}       any other refusal
     {:status :invalid  :explanation <malli>}

   Load and coercion exceptions propagate; the caller decides how to report
   them. Both the human report below and the recorded baseline read this one
   function, so they cannot disagree about what a filing resolves to."
  [path instant]
  (if-not (plan-valid? path)
    {:status :invalid :explanation (coerce/explain schema/RatePlan (load-plan! path))}
    ;; See `legitimate-refusals`: a refusal with one of those reasons is the
    ;; right answer, not a failure. Any other refusal still fails.
    (try
      (let [resolved (price/resolve-prices (load-plan! path) instant
                                           {:profile-alternatives (nominations-for (load-plan! path))})]
        {:status  :ok
         :ledgers (count (:urpx.resolved/ledgers resolved))
         :rate    (price/marginal-unit-rate resolved)})
      (catch Exception e
        (let [data   (ex-data e)
              reason (:reason data)]
          (if (or (legitimate-refusals reason) (expired-before? data instant)
                  (not-yet-effective? data instant))
            {:status :refused :reason (refusal-reason data instant)}
            {:status :error :error (.getMessage e)}))))))

(defn- validate-rate-plan [path]
  (let [r (probe-plan path probe-instant)]
    (case (:status r)
      :invalid (do (println "validate ✗")
                   (println "    explain:" (pr-str (:explanation r)))
                   false)
      :ok      (do (swap! marginal-count inc)
                   (println (format "load+coerce ✓ resolve ✓  (%d ledgers, marginal=%s)"
                                    (:ledgers r) (:rate r)))
                   true)
      :refused (do (note-refusal! (:reason r))
                   (println (format "load+coerce ✓ resolve ✓  (%s; %s)"
                                    (name (:reason r))
                                    (case (:reason r)
                                      :outside-version-window "this version had ended by the probe instant"
                                      :not-yet-effective "this version had not begun by the probe instant"
                                      "nothing priced per kWh here")))
                   true)
      :error   (do (println (format "load+coerce ✓ resolve ✗  %s" (:error r)))
                   false))))

;; A modifier version whose window has closed at the instant is refused before
;; it reaches clj-urpx. clj-urpx checks an adjusting urpx:ServiceBracket's
;; target "at any instant", ahead of the version window, so composing
;; sce:tou-d-4-9pm-hpwh-2025-11-15 with the base version in force in 2026
;; refused :unresolvable-adjusted-tier: its targets are the 2025-11-15 tiers,
;; which that base no longer carries. The answer the window gives is the one
;; every other expired modifier version already records.
(defn- expired-modifier?
  "True when every version of `modifier` has ended by `instant`."
  [modifier ^java.time.ZonedDateTime instant]
  (let [v  (:urpx/hasRatePlanModifierVersion modifier)
        vs (if (map? v) [v] v)
        at (.toLocalDateTime instant)]
    (and (seq vs)
         (every? (fn [ver]
                   (when-let [exp (some-> (:urpx/expirationDateTime ver) as-local)]
                     (not (.isAfter exp at))))
                 vs))))

;; The mirror case: a modifier version that has not begun at the instant.
;; sce:tou-d-4-9pm-hpwh-2026-10-01 targets the 2026-10-01 tiers, which the
;; base version composed at a summer 2026 probe does not carry, so clj-urpx
;; refuses :unresolvable-adjusted-tier before it reaches the version window.
;; That refusal, from a modifier whose every version begins after the
;; instant, is recorded as :not-yet-effective. Other not-yet-effective
;; modifiers are left to clj-urpx as before.
(defn- unstarted-modifier?
  "True when every version of `modifier` begins after `instant`."
  [modifier ^java.time.ZonedDateTime instant]
  (let [v  (:urpx/hasRatePlanModifierVersion modifier)
        vs (if (map? v) [v] v)
        at (.toLocalDateTime instant)]
    (and (seq vs)
         (every? (fn [ver]
                   (when-let [eff (some-> (:urpx/effectiveDateTime ver) as-local)]
                     (.isAfter eff at)))
                 vs))))

(defn- compose-modifier-with-base
  "Compose `modifier` into the latest version of `base-kw`'s base RatePlan
   filing, resolved at `instant`. Returns a map: :status ∈ #{:ok :refused :no-corpus-base :error},
   plus :ledgers + :rate + :base-version on :ok, or :reason on :refused, or
   :error. Like `probe-plan` it neither prints nor tallies, so the human
   report and the recorded baseline read the same result.

   :base-version is the date of the base filing actually used. A newer base
   version landing changes which filing this composes against, and that is a
   change the recorded baseline should show rather than absorb.

   :refused is a PASS. A composition can legitimately price nothing per kWh:
   CPAU E-14 is street lighting, and composing the hydroelectric adjustment
   onto it contributes one energy ledger whose every tier is event-driven. See
   `legitimate-refusals` for why accepting these does not make the gate
   vacuous."
  [modifier base-kw base-iri-lookup instant]
  (if-let [base-info (some-> (get base-iri-lookup base-kw) seq (base-at instant))]
    (let [base (load-plan! (:path base-info))]
      (if (expired-modifier? modifier instant)
        {:status :refused :reason :outside-version-window :base-version (:date base-info)}
        (try
          (let [resolved (price/resolve-prices-with-modifiers base [modifier] instant
                                                              {:profile-alternatives (nominations-for base modifier)})]
            {:status       :ok
             :base-version (:date base-info)
             :ledgers      (count (:urpx.resolved/ledgers resolved))
             :rate         (price/marginal-unit-rate resolved)})
          (catch Exception e
            (let [data     (ex-data e)
                  reason   (:reason data)
                  mod-iri  (:jsonld/id modifier)
                  expected (get condition-gated-expected mod-iri)
                  unstarted (and (= reason :unresolvable-adjusted-tier)
                                 (unstarted-modifier? modifier instant))
                  ok?      (or (legitimate-refusals reason)
                               (expired-before? data instant)
                               (not-yet-effective? data instant)
                               unstarted
                               (and (= reason :condition-gated-tier) (some? expected)))]
              (if ok?
                {:status :refused
                 :reason (if unstarted :not-yet-effective (refusal-reason data instant))
                 :base-version (:date base-info)}
                {:status :error :error (.getMessage e) :base-version (:date base-info)}))))))
    {:status :no-corpus-base}))

(defn- validate-rate-plan-modifier [path pairings base-iri-lookup]
  (let [modifier (load-modifier! path)]
    (if-not (modifier-valid? path)
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
          (let [results  (mapv #(assoc (compose-modifier-with-base modifier % base-iri-lookup
                                                                   probe-instant)
                                       :base %)
                               base-kws)
                _        (doseq [r results]
                           (case (:status r)
                             :ok      (swap! marginal-count inc)
                             :refused (note-refusal! (:reason r))
                             nil))
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
                                           (:rate (first ok)))
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

(defn- validate-withheld
  "Load, coerce and Malli-validate a filing withheld from resolution, and
   resolve nothing: see dev/withheld-filings.json."
  [kind path]
  (if (case kind
        :rate-plan          (plan-valid? path)
        :rate-plan-modifier (modifier-valid? path))
    (do (println "load+coerce ✓  withheld from resolution (dev/withheld-filings.json)") true)
    (do (println "validate ✗") false)))

(defn validate-one [width [kind label path] pairings base-iri-lookup]
  (print (pad label width) "")
  (flush)
  (try
    (boolean
     (if (layout/withheld? "." path)
       (validate-withheld kind path)
       (case kind
         :rate-plan          (validate-rate-plan path)
         :rate-plan-modifier (validate-rate-plan-modifier path pairings base-iri-lookup))))
    (catch Exception e
      (println "load+coerce ✗  " (.getMessage e))
      false)))

;; --- the marginal-rate baseline ----------------------------------------------
;;
;; WHY THIS EXISTS. Everything above computes a marginal unit rate and prints
;; it. Nothing above ASSERTS on it. The only value-shaped guard is the
;; anti-vacuity refusal at the end of -main, which fires solely when NO filing
;; produced a rate at all, so any individual rate could take any value and the
;; run still read green. It did: three NBT compositions resolved to -213, -218
;; and -260 dollars per kWh while this gate reported 73/73 passed.
;;
;; WHY NOT A BOUND. A strictly-positive bound was tried and rejected. Three of
;; the corpus's numeric resolutions are legitimately negative (export credits
;; make a negative marginal rate meaningful), so the bound fires on correct
;; values; and a wrong rate that stays positive sails through it, so it misses
;; the defects it was built for. A bound encodes a guess about the range. A
;; recorded value encodes the actual answer.
;;
;; WHAT THIS DOES INSTEAD. Every resolvable thing in the corpus, base filing
;; and modifier/base composition alike, gets a row in a checked-in file. The
;; check compares the tree against that file and fails on any row whose value
;; moved. Movement is then a diff to review, not a number to eyeball.
;;
;; WHAT MAKES IT NOT VACUOUS. Three properties, each of which the checks below
;; refuse (exit 3) rather than pass when it fails:
;;
;;   TOTAL       A refusal is a row carrying its reason, not an absent row.
;;               Without that, the way to silence a row would be to make it
;;               refuse, and silence would read as agreement.
;;   DELIBERATE  Re-recording is its own command that nothing else invokes.
;;               A baseline the gate refreshes when it differs asserts
;;               nothing at all: it agrees with whatever it is shown. Neither
;;               dev/gate.sh nor dev/check_all.py nor dev/git-hooks/pre-commit
;;               writes this file (see `record-baseline!`).
;;   DENOMINATED The check reports how many recorded VALUES it compared, and
;;               refuses when that count is zero. A corpus that stops
;;               resolving, a baseline that loses its rows, or a rename that
;;               makes every key miss all collapse the denominator, and each
;;               of them would otherwise leave 0 differences and a green exit.

(def baseline-file "dev/baseline/marginal-rates.edn")

(defn- clj-urpx-version
  "The consumer version this run resolved under, read from deps.edn. Recorded
   as context: a rate that moves because clj-urpx moved is still a rate that
   moved, and the reviewer of the diff wants to know which."
  []
  (try
    (-> (slurp "deps.edn") edn/read-string
        (get-in [:deps 'energy.grid-coordination/clj-urpx :mvn/version]))
    (catch Exception _ nil)))

(defn- row-of
  "The recorded form of a probe result. Small and stable: the Malli
   explanation and nothing else large is kept, and the rate is stored as the
   string the BigDecimal prints to, so the file diffs as text."
  [r]
  (cond-> {:status (:status r)}
    (:reason r)       (assoc :reason (:reason r))
    (:base-version r) (assoc :base-version (:base-version r))
    (:ledgers r)      (assoc :ledgers (:ledgers r))
    (:rate r)         (assoc :rate (str (:rate r)))
    (:error r)        (assoc :error (:error r))))

(defn- at-each-instant
  "`(f instant)` at every probe instant, as {instant-id -> row}, in the order
   `probe-instants` declares. Every corpus key carries a cell for every
   instant, including the ones that refuse: the grid is rectangular, which is
   what lets the check below report a per-instant denominator."
  [f]
  (reduce (fn [m probe] (assoc m (:id probe) (row-of (f (:at probe)))))
          {}
          probe-instants))

(defn- collect-rows
  "Every filing in the corpus, resolved at every probe instant, as an ordered
   {key -> {instant-id -> row}}. Over the corpus a base filing contributes one
   key, a modifier contributes one key per declared base, and a filing that
   resolves to nothing still contributes a key saying so. Each key then
   contributes one cell per instant.

   Keys are paths, not labels, because a path is what a reviewer greps for and
   because two filings can share a label across versions. The instant id is a
   separate level rather than part of the key so that a filing's instants sit
   together in the recorded file and a diff reads down one filing at a time."
  [filings pairings base-iri-lookup]
  (into (sorted-map)
        (mapcat
         (fn [[kind _ path]]
           (try
             (case kind
               :rate-plan
               [[(str "plan|" path) (at-each-instant #(probe-plan path %))]]

               :rate-plan-modifier
               (let [modifier (load-modifier! path)
                     v        (:urpx/hasRatePlanModifierVersion modifier)
                     versions (if (map? v) [v] v)]
                 (cond
                   (not (modifier-valid? path))
                   [[(str "modifier|" path) (at-each-instant (constantly {:status :invalid}))]]

                   ;; A modifier version in effect at none of the probe instants
                   ;; (superseded before the first, or not yet effective at the
                   ;; last) gets no compose keys. Composed with a current base it
                   ;; describes a pairing no customer has, and where its charge
                   ;; never enters the per-kWh marginal (sce:deed-restricted's
                   ;; per-day credit) such a cell recorded :ok while the library
                   ;; marked the ledger outside its window. One row records why
                   ;; it is not probed.
                   (not-any? (fn [{:keys [^java.time.ZonedDateTime at]}]
                               (some #(price/version-covers? % at (.getZone at)) versions))
                             probe-instants)
                   [[(str "modifier|" path) (at-each-instant (constantly {:status :outside-every-probe}))]]

                   :else
                   (let [base-kws (get-in pairings
                                          [:by-modifier (iri->kw (:jsonld/id modifier))
                                           :applicable-to])]
                     (if (empty? base-kws)
                       [[(str "modifier|" path) (at-each-instant (constantly {:status :no-bases}))]]
                       (for [b (sort base-kws)]
                         [(str "compose|" path "|" (kw->iri b))
                          (at-each-instant #(compose-modifier-with-base
                                             modifier b base-iri-lookup %))]))))))
             (catch Exception e
               ;; A filing that will not load fails at every instant alike, and
               ;; recording it that way keeps the grid rectangular.
               [[(str "plan|" path)
                 (at-each-instant (constantly {:status :load-error :error (.getMessage e)}))]])))
         ;; Withheld filings get no rows at all: the pinned clj-urpx would
         ;; record a wrong rate for them. See dev/withheld-filings.json.
         (remove (fn [[_ _ path]] (layout/withheld? "." path)) filings))))

(defn- cells
  "The {key -> {instant-id -> row}} grid flattened to {[key instant-id] -> row}.
   Comparison, counting and refusal all work on cells: a row is what a filing
   resolves to AT AN INSTANT, and the instant is half of its identity."
  [rows]
  (into {} (for [[k by-instant] rows [id r] by-instant] [[k id] r])))

(defn- numeric
  "Cells carrying an actual resolved value. This is the denominator every
   refusal below is measured against."
  [cells]
  (into {} (filter #(= :ok (:status (val %))) cells)))

(defn- per-instant-ok
  "{instant-id -> how many of `cells` resolved to a rate there}. A probe whose
   count is zero asserted nothing at all, and the checks below refuse rather
   than pass on one."
  [cells]
  (reduce (fn [m [[_ id] r]] (update m id (fnil + 0) (if (= :ok (:status r)) 1 0)))
          (into {} (map (juxt :id (constantly 0))) probe-instants)
          cells))

(defn- rate= [a b]
  (cond
    (= a b)                true
    (or (nil? a) (nil? b)) false
    ;; Compared by value, not by printed form: a scale change (0.5868 vs
    ;; 0.58680) is the same rate and should not fire.
    :else (try (zero? (.compareTo (bigdec a) (bigdec b)))
               (catch Exception _ false))))

(defn- row= [a b]
  (and (= (:status a) (:status b))
       (= (:reason a) (:reason b))
       (= (:ledgers a) (:ledgers b))
       (= (:base-version a) (:base-version b))
       (= (:error a) (:error b))
       (rate= (:rate a) (:rate b))))

(defn- describe
  "One row rendered for a diff line. Every field `row=` compares appears here,
   so a CHANGED pair never renders identically on both sides."
  [r]
  (str (case (:status r)
         :ok         (str (:rate r) " over " (:ledgers r) " ledger(s)")
         :refused    (str "refused " (name (:reason r)))
         :error      (str "error " (pr-str (:error r)))
         :load-error (str "load-error " (pr-str (:error r)))
         (name (:status r)))
       (when (:base-version r) (str ", base " (:base-version r)))))

(defn- record-baseline!
  "Write the baseline. NOTHING CALLS THIS BUT AN EXPLICIT --record-baseline.
   It is deliberately absent from dev/gate.sh, from dev/check_all.py's
   generator list, and therefore from the pre-commit hook, which regenerates
   and stages only reports/. A baseline regenerated whenever it disagrees with
   the tree is an assertion that the tree equals itself."
  [rows]
  (let [cs         (cells rows)
        n          (count (numeric cs))
        by-instant (per-instant-ok cs)
        barren     (sort (keep (fn [[id c]] (when (zero? c) id)) by-instant))]
    (when (zero? n)
      (println "REFUSED: not one filing or composition produced a marginal unit rate,")
      (println "         so this baseline would assert nothing. Refusing to record it.")
      (System/exit 3))
    ;; A probe instant that resolves nothing anywhere asserts nothing, and a
    ;; column of pure refusals recorded as though it were evidence is exactly
    ;; the shape of gate this file exists to not be. It means the instant fell
    ;; outside every filing's validity window, so fix the instant.
    (when (seq barren)
      (println (format "REFUSED: %d probe instant(s) resolved no rate at all: %s."
                       (count barren) (str/join ", " barren)))
      (println "         An instant that refuses everywhere records a column of")
      (println "         nothing. Check it against the corpus's startDate range.")
      (System/exit 3))
    (io/make-parents baseline-file)
    (spit baseline-file
          (str ";; Resolved marginal unit rates: one block per base filing and per\n"
               ";; modifier/base composition, and inside each block one row per probe\n"
               ";; instant. The instants, and why each is there, are in the probe-instants\n"
               ";; list in dev/validate_v020.clj.\n"
               ";;\n"
               ";; NOT auto-generated. No gate, generator or git hook writes this file.\n"
               ";; Re-record deliberately and review the diff:\n"
               ";;\n"
               ";;     clojure -M:validate --record-baseline\n"
               ";;\n"
               ";; Compared by `clojure -M:validate --check-baseline`, which dev/gate.sh\n"
               ";; runs in both --fast and --full. See the baseline section of\n"
               ";; dev/validate_v020.clj for why a recorded value and not a bound.\n"
               "{:probe-instants\n"
               " [" (str/join "\n  " (for [{:keys [id at]} probe-instants]
                                       (pr-str {:id id :at (str at)}))) "]\n"
               " :clj-urpx-version " (pr-str (clj-urpx-version)) "\n"
               " :rows\n"
               " {"
               (str/join "\n\n  "
                         (for [[k by-id] rows]
                           (str (pr-str k) "\n  {"
                                (str/join "\n   "
                                          (for [{:keys [id]} probe-instants
                                                :let [r (get by-id id)]
                                                :when r]
                                            (str (pr-str id) " " (pr-str r))))
                                "}")))
               "}}\n"))
    (println (format "wrote %s" baseline-file))
    (println (format "  %d filing row(s) x %d probe instant(s) = %d cells, %d carrying a"
                     (count rows) (count probe-instants) (count cs) n))
    (println (format "  resolved rate, %d refusing"
                     (count (filter #(= :refused (:status (val %))) cs))))
    (doseq [{:keys [id]} probe-instants]
      (println (format "    %-26s %3d rate(s)" id (get by-instant id))))
    (System/exit 0)))

(defn- check-baseline
  "Compare `rows` against the recorded file, cell by cell, where a cell is one
   filing row at one probe instant. Exit 0 identical, 1 a recorded value moved,
   2 cells appeared or vanished, 3 refused."
  [rows]
  (when-not (.exists (io/file baseline-file))
    (println (format "REFUSED: no baseline at %s." baseline-file))
    (println "         Record one deliberately: clojure -M:validate --record-baseline")
    (System/exit 3))
  (let [file         (edn/read-string (slurp baseline-file))
        recorded     (cells (:rows file))
        now          (cells rows)
        ;; An id whose recorded instant is not the instant the code now probes
        ;; is not a value that moved, it is a different question. Comparing the
        ;; two would report a corpus regression for an edit to this file, so
        ;; those cells are set aside and named instead.
        recorded-ats (into {} (map (juxt :id :at)) (:probe-instants file))
        redefined    (into #{} (keep (fn [{:keys [id at]}]
                                       (when-let [was (get recorded-ats id)]
                                         (when (not= was (str at)) id)))
                                     probe-instants))
        comparable   (fn [[_ id]] (not (redefined id)))
        shared       (sort (filter #(and (contains? now %) (comparable %)) (keys recorded)))
        changed      (remove #(row= (get recorded %) (get now %)) shared)
        added        (sort (remove #(contains? recorded %) (keys now)))
        missing      (sort (remove #(contains? now %) (keys recorded)))
        compared     (count (filter #(= :ok (:status (get recorded %))) shared))
        per-instant  (reduce (fn [m k]
                               (cond-> m
                                 (= :ok (:status (get recorded k)))
                                 (update (second k) (fnil inc 0))))
                             (into {} (map (fn [k] [(second k) 0])) shared)
                             shared)
        barren       (sort (keep (fn [[id c]] (when (zero? c) id)) per-instant))]
    (when (empty? recorded)
      (println (format "REFUSED: %s records no rows." baseline-file))
      (System/exit 3))
    (doseq [id (sort redefined)]
      (println (format "  REDEFINED  probe instant %s: recorded at %s, now %s"
                       id (get recorded-ats id)
                       (str (:at (first (filter #(= id (:id %)) probe-instants)))))))
    ;; The denominator. Zero here means no recorded VALUE was tested: a corpus
    ;; that stopped resolving, a rename that made every key miss, or a baseline
    ;; of nothing but refusals. Each leaves zero differences and would
    ;; otherwise exit green.
    (when (zero? compared)
      (println (format "REFUSED: %d recorded cell(s), %d resolved now, but not one"
                       (count recorded) (count now)))
      (println "         recorded RATE was compared. Nothing was asserted, so this run")
      (println "         proves nothing. Refusing to report it as a pass.")
      (System/exit 3))
    ;; The same denominator, per instant. A widened probe set fails the way a
    ;; single one did if one column quietly stops asserting: the corpus-wide
    ;; count stays healthy on the strength of the other instants while that
    ;; instant covers nothing. An instant with no comparable recorded rate is
    ;; either newly added (re-record) or newly outside every validity window.
    (when (seq barren)
      (println (format "REFUSED: probe instant(s) %s compared no recorded rate."
                       (str/join ", " barren)))
      (println "         That column asserts nothing, so this run does not prove what")
      (println "         it appears to. Re-record deliberately, or fix the instant.")
      (System/exit 3))
    (doseq [[k id] changed]
      (println (format "  CHANGED  %s @ %s\n             %s  ->  %s"
                       k id (describe (get recorded [k id])) (describe (get now [k id])))))
    (doseq [[k id] added]
      (println (format "  NEW      %s @ %s  =  %s" k id (describe (get now [k id])))))
    (doseq [[k id] missing]
      (println (format "  GONE     %s @ %s  was %s" k id (describe (get recorded [k id])))))
    (let [recorded-version (:clj-urpx-version file)
          now-version      (clj-urpx-version)]
      (when (and recorded-version now-version (not= recorded-version now-version))
        (println (format "  note: baseline recorded under clj-urpx %s, running %s"
                         recorded-version now-version))))
    (println (format "marginal-rate baseline: %d instants, %d recorded cell(s), %d resolved, %d rate(s) compared, %d changed, %d new, %d gone"
                     (count probe-instants) (count recorded) (count now) compared
                     (count changed) (count added) (count missing)))
    (cond
      (seq changed)
      (do (println (format "\n%d recorded value(s) moved, over %d instant(s): %s."
                           (count changed)
                           (count (distinct (map second changed)))
                           (str/join ", " (sort (distinct (map second changed))))))
          (println "Account for each one, then re-record deliberately:")
          (println "clojure -M:validate --record-baseline")
          (System/exit 1))

      (or (seq added) (seq missing) (seq redefined))
      (do (println (format "\n%d cell(s) appeared, %d vanished and %d probe instant(s) were"
                           (count added) (count missing) (count redefined)))
          (println "redefined; no recorded rate moved.")
          (println "Re-record deliberately: clojure -M:validate --record-baseline")
          (System/exit 2))

      :else (System/exit 0))))

;; --- references across documents --------------------------------------------
;;
;; urpx.index/mistyped-references judges a reference by the @type of the node it
;; names, and only nodes in the documents it is given can be named. The corpus is
;; loaded here as one set, so a reference into another filing, such as a
;; modifier's to its base, is judged against the node it lands on there.

(defn- subject-of
  "The @id of the node holding the reference at path `in` within `doc`: the
   deepest node on the path that carries one, so a reference held by a blank
   node is reported against its nearest named ancestor."
  [doc in]
  (->> (range (count in))
       (map #(get-in doc (subvec in 0 %)))
       (keep #(when (map? %) (:jsonld/id %)))
       last))

(defn- mistyped-hits
  "urpx.index/mistyped-references over every top-level node of every filing at
   `paths`, judged as one set, as [{:path :subject :property :target :types
   :range}]. A filing that does not load is skipped: it has already failed the
   run."
  [paths]
  (let [owned (vec (for [path paths
                         node (try (load-graph! path) (catch Exception _ nil))]
                     [path node]))]
    (vec (for [{:keys [document in property id types] class :range}
               (index/mistyped-references (mapv second owned))
               :let [[path node] (nth owned document)
                     in          (vec in)]]
           {:path     path
            :subject  (subject-of node in)
            :property property
            :target   (or id "inline node")
            :types    types
            :range    class}))))

(defn- validate-corpus []
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
    ;; ZONE INVARIANCE. A ZonedDateTime denotes an INSTANT, so one moment spelled
    ;; two ways must resolve to one answer. Nothing here asserted that, because
    ;; every probe instant above is Pacific, and that blind spot hid a real
    ;; defect: at clj-urpx 0.30.0 the caller's zone was discarded with
    ;; .toLocalDateTime and compared against bounds naive in the PLAN's zone, so
    ;; PG&E E-TOU-C returned 0.34586 at 10:00 Pacific and 0.46886 for the same
    ;; instant written in UTC, 36% apart, with no error and no mark. Fixed in
    ;; 0.31.0. This check is here so a Pacific-only probe set cannot hide its
    ;; return: it re-asks every probe instant in UTC and in Asia/Tokyo, which
    ;; are the same moments, and requires the same answers.
    (let [zones ["UTC" "Asia/Tokyo"]
          plans (->> filings (filter #(= :rate-plan (first %))) (map #(nth % 2)) sort (take 6))
          mism  (atom [])]
      (doseq [path plans
              {:keys [id at]} probe-instants
              z zones]
        (let [other (.withZoneSameInstant ^java.time.ZonedDateTime at (java.time.ZoneId/of z))
              answer (fn [zdt] (try (str (:rate (probe-plan path zdt)))
                                    (catch Exception e (str "threw " (.getMessage e)))))
              a (answer at) b (answer other)]
          (when-not (= a b)
            (swap! mism conj (format "%s @ %s: %s in %s, %s in %s"
                                     path id a (str (.getZone ^java.time.ZonedDateTime at)) b z)))))
      (if (seq @mism)
        (do (println)
            (println (format "REFUSED: %d resolution(s) depend on how the instant was SPELLED, not on the instant."
                             (count @mism)))
            (doseq [m (take 8 @mism)] (println "        " m))
            (System/exit 1))
        (println (format "zone invariance: %d plan(s) x %d instant(s) x %d zone(s) agree"
                         (count plans) (count probe-instants) (count zones)))))

    (let [paths (map #(nth % 2) filings)
          hits  (mistyped-hits paths)]
      (if (seq hits)
        (do (println)
            (println (format "MISTYPED: %d reference(s) or inline node(s) of the wrong class, judged across %d filing(s):"
                             (count hits) (count paths)))
            (doseq [{:keys [path subject property target types] class :range} hits]
              (println (format "    ✗ %s  %s %s -> %s is %s, takes %s"
                               path subject (kw->iri property) target (str/join "/" types) class)))
            (System/exit 1))
        (println (format "mistyped references: none across %d filing(s) loaded as one set"
                         (count paths)))))

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

(defn -main [& args]
  (let [mode (cond (some #{"--record-baseline"} args) :record
                   (some #{"--check-baseline"} args)  :check
                   :else                              :validate)]
    (if (= mode :validate)
      (println "Report instant:" probe-instant)
      (println (format "Probe instants: %d, %s .. %s"
                       (count probe-instants)
                       (:id (first probe-instants))
                       (:id (last probe-instants)))))
    (println)
    (when (empty? filings)
      (println "ERROR: corpus discovery found no filings under us/. The tree moved")
      (println "       and this script was not updated, or this is not the repo root.")
      (println "       Refusing to report 0/0 as success.")
      (System/exit 3))
    (when (not= mode :validate)
      (let [rows (collect-rows filings (read-pairings) (build-base-iri-lookup filings))]
        (when (empty? rows)
          (println "REFUSED: the corpus resolved to no rows at all.")
          (System/exit 3))
        (if (= mode :record)
          (record-baseline! rows)
          (check-baseline rows)))))
  (validate-corpus))
