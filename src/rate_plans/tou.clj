;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.tou
  "Expand a time-of-use rate plan written as tables into a urpx:URPXPackage.
   IRIs follow <prefix>:<schedule>-<version>-<part>. Knows nothing about any
   utility."
  (:require [clojure.string :as str]
            [rate-plans.urpx :as u]
            [urpx.dsl :as dsl])
  (:import (java.time DayOfWeek LocalDate)))

;; ---------------------------------------------------------------------------
;; Holidays
;; ---------------------------------------------------------------------------

(defn observed-mondays
  "[[key name date-string] ...], sorted by date: the Monday after each
   fixed-date holiday in `of` that falls on a Sunday, from `first-year`
   through the calendar's :through year."
  [{:keys [named]
    {:keys [of through]} :observed-monday-after-sunday}
   first-year]
  (let [rows (into {}
                   (map (juxt first identity))
                   named)]
    (->> (for [y (range first-year (inc through))
               k of
               :let [[_ n _ [mo d]] (rows k)
                     day (LocalDate/of (int y) (int mo) (int d))]
               :when (= DayOfWeek/SUNDAY (.getDayOfWeek day))]
           [k n (str (.plusDays day 1))])
         (sort-by #(nth % 2)))))

(defn holiday-calendar [id calendar year]
  (dsl/holiday-calendar
   {:as (id "holidays")
    :has-holiday
    (into (mapv (fn [[k n rule]]
                  (dsl/holiday
                   {:as (id "holiday" k)
                    :holiday-name n
                    :holiday-rule rule}))
                (:named calendar))
          (map (fn [[k n date]]
                 (dsl/holiday
                  {:as (id "holiday" k date)
                   :holiday-name (str n " (observed)")
                   :holiday-date date})))
          (observed-mondays calendar year))}))

;; ---------------------------------------------------------------------------
;; TOU schedule
;; ---------------------------------------------------------------------------

(defn- camel [k]
  (let [[w & ws] (str/split (name k) #"-")]
    (apply str
           w
           (map str/capitalize ws))))

(def days
  {:all     nil
   :mon-sat [:urpx/monday :urpx/tuesday :urpx/wednesday :urpx/thursday :urpx/friday :urpx/saturday]
   :mon-fri [:urpx/monday :urpx/tuesday :urpx/wednesday :urpx/thursday :urpx/friday]
   :sat-sun [:urpx/saturday :urpx/sunday]
   :sat     [:urpx/saturday]
   :sun     [:urpx/sunday]})

(defn- bracket [id [period slug day-set start end holidays]]
  (let [ds (days day-set)]
    (dsl/time-bracket
     {:as (id "time-bracket" period slug)
      :start-time (u/xsd-time start)
      :end-time (u/xsd-time end)
      :day-type (if ds :urpx/customDays :urpx/allDays)
      :days-of-week ds
      :include-holidays (case holidays
                          :excluded false
                          :only true
                          nil)
      :include-non-holidays (when (= holidays :only)
                              false)})))

(defn- tou-schedule [id periods brackets]
  (dsl/tou-schedule
   {:as (id "tou-schedule")
    :references-metric-input [(id "mi-energy")]
    :has-tou-tier
    (vec (map-indexed
          (fn [i [k label period-name]]
            (dsl/tou-tier
             {:as (id "tou-tier" k)
              :tier-source-name (str "Energy " label)
              :tou-tier-standard-name (keyword "urpx"
                                               (str (camel k) "Tier"))
              :tou-tier-number (inc i)
              :has-tou-period
              [(dsl/tou-period
                {:as (id "tou-period" k)
                 :name period-name
                 :tou-period-number (inc i)
                 :has-time-bracket (->> brackets
                                        (filter #(= k (first %)))
                                        (mapv #(bracket id %)))})]}))
          periods))}))

;; ---------------------------------------------------------------------------
;; Charges: one daily per-meter charge and one TOU energy charge
;; ---------------------------------------------------------------------------

(defn ids
  "The keywords naming what another document may reference in this plan's
   version `date`, with their @types."
  [prefix schedule date fixed]
  (let [id (u/ider (keyword prefix (str schedule "-" date)))]
    {:summary-energy [(id "summary-energy") "urpx:PriceSummary"]
     :price-fixed [(id "price" fixed) "urpx:Price"]}))

(defn- charges [id {:keys [identifier version rates tou-periods price-summary]}]
  (let [sched (str "(Schedule " identifier ")")
        fixed (first (remove (set (map first tou-periods))
                             (keys rates)))
        fixed-name (str/join " "
                             (map str/capitalize
                                  (str/split (name fixed) #"-")))
        energy-prices (mapv (fn [[k label]]
                              (dsl/price
                               {:as (id "price-energy-charge" k)
                                :references-price-definition (id "pd-energy-charge" k)
                                :name (str "Energy " label)
                                :unit-price (u/hundredths (rates k))}))
                            tou-periods)]
    {:ledgers
     [(u/ledger (id "ledger-energy-charge")
                (str "Time-of-Use Energy Charge " sched)
                (id "mi-energy"))
      (u/ledger (id "ledger" fixed)
                fixed-name
                (id "mi-meter-count"))]
     :price-definitions
     (conj (vec (map-indexed
                 (fn [i [k label]]
                   (dsl/price-definition
                    {:as (id "pd-energy-charge" k)
                     :name (str "Energy Charge, " label " " sched)
                     :charge-type :urpx/usageCharge
                     :charge-category :urpx/auxiliaryCharge
                     :bill-portion :urpx/bundledPortion
                     :tou-period-number (inc i)
                     :references-ledger (id "ledger-energy-charge")}))
                 tou-periods))
           (dsl/price-definition
            {:as (id "pd" fixed)
             :name (str fixed-name ", per meter per day " sched)
             :charge-type :urpx/customerCharge
             :charge-category :urpx/serviceCharge
             :bill-portion :urpx/bundledPortion
             :base-quantity 1
             :has-calculation-method (u/per-day (id "pd" fixed "calculation-method"))
             :references-ledger (id "ledger" fixed)}))
     :prices
     (dsl/prices
      {:as (id "prices")
       :has-price [(dsl/price
                    {:as (id "price" fixed)
                     :references-price-definition (id "pd" fixed)
                     :start-date version
                     :name fixed-name
                     :unit-price (u/hundredths (rates fixed))})]
       :has-price-set
       [(dsl/price-set
         {:as (id "ps-energy-charge")
          :start-date version
          :has-price energy-prices
          :has-price-summary
          (when price-summary
            [(dsl/price-summary
              {:as (id "summary-energy")
               :name price-summary
               :includes-price (mapv (fn [[k]]
                                       (id "price-energy-charge" k))
                                     tou-periods)})])})]})}))

;; ---------------------------------------------------------------------------
;; Package
;; ---------------------------------------------------------------------------

(defn package
  "One RatePlan with one RatePlanVersion, from a plan map (see the SCL
   schedule namespaces for the keys)."
  [{:keys [utility schedule version next source pages calendar] :as plan}]
  (dsl/dsl-scope
   (let [[p] (:prefix utility)
         id (u/ider (keyword p (str schedule "-" version)))
         {:keys [ledgers price-definitions prices]} (charges id plan)
         cc (keyword p (str "cc-" schedule "-" version))]
     (dsl/urpx-package
      {:as (keyword p (str "doc-" schedule "-" version))
       :target-urpx-version u/urpx-version
       :has-rate-plan
       [(dsl/rate-plan
         {:as (keyword p schedule)
          :name (:name plan)
          :rate-plan-unique-identifier (:identifier plan)
          :initial-effective-date (:initial-effective-date plan)
          :timezone-identifier (:timezone utility)
          :has-rate-plan-version
          (dsl/rate-plan-version
           {:as (id)
            :description (:description plan)
            :effective-date-time (str version "T00:00:00")
            :expiration-date-time (some-> next
                                          (str "T00:00:00"))
            :change-reason :urpx/rateCase
            :price-currency "USD"
            :commodity [:urpx/electricity]
            :service-role :urpx/bundledServiceRole
            :customer-choice (:customer-choice plan)
            :is-default (:default? plan)
            :has-data-source-reference [(u/data-source source pages)]
            :has-eligibility-rule
            [(u/customer-kind-rule (u/ider (id "er-residential"))
                                   (:eligibility plan))]
            :has-plan-elements
            (dsl/plan-elements
             {:as (id "plan-elements")
              :has-holiday-calendar
              (holiday-calendar id
                                calendar
                                (parse-long (subs version 0 4)))
              :has-metric-input (u/metric-inputs id p)
              :has-billing-model
              (dsl/billing-model
               {:as (id "plan-elements-billing-model")
                :has-tou-schedule
                [(tou-schedule id
                               (:tou-periods plan)
                               (:tou-brackets plan))]
                :has-ledger ledgers
                :has-price-definition price-definitions})})
            :has-prices prices
            :offered-by (u/utility-operator utility)
            :for-rate-plan (keyword p schedule)
            :has-coverage-claim
            (u/coverage-claim cc
                              (get-in plan [:coverage :result])
                              (assoc (:coverage plan)
                                     :evaluated-on
                                     (:evaluated-on source)))})})]}))))

;; ---------------------------------------------------------------------------
;; Prose generated from the tables
;; ---------------------------------------------------------------------------

(defn- clock
  "17:00 -> \"5 p.m.\" (:long) or \"5pm\" (:compact)."
  [fmt hhmm]
  (let [[h m] (map parse-long (str/split hhmm #":"))
        h (mod h 24)
        h12 (if (zero? (mod h 12))
              12
              (mod h 12))
        mm (when (pos? m)
             (format ":%02d" m))]
    (case fmt
      :long (str h12
                 mm
                 (if (< h 12) " a.m." " p.m."))
      :compact (str h12
                    mm
                    (if (< h 12) "am" "pm")))))

(defn hours-phrases
  "{period-key phrase}: each period's hours in words, from the bracket table.
   Brackets with the same day set (a holiday-only bracket is the set
   :holiday) share one phrase; adjacent sets with equal hours merge into a
   vector key such as [:sun :holiday]. Style keys: :clock (:long or
   :compact), :range (between start and end), :group-sep, :day-words, and
   :holiday-free (appended when a period excludes holidays and has no
   holiday-only bracket)."
  [brackets {:keys [clock-fmt range group-sep day-words holiday-free]}]
  (into {}
        (for [[k bs] (group-by first brackets)
              :let [set-of (fn [[_ _ d _ _ h]]
                             (if (= h :only) :holiday d))
                    groups (for [g (partition-by set-of bs)]
                             {:days (set-of (first g))
                              :hours (str/join " and "
                                               (for [[_ _ _ s e] g]
                                                 (str (clock clock-fmt s)
                                                      range
                                                      (clock clock-fmt e))))})
                    merged (reduce (fn [acc {:keys [days hours]}]
                                     (let [prev (peek acc)]
                                       (if (and prev
                                                (= hours (:hours prev)))
                                         (conj (pop acc)
                                               (update prev
                                                       :days
                                                       #(conj (if (vector? %) % [%])
                                                              days)))
                                         (conj acc {:days days :hours hours}))))
                                   []
                                   groups)
                    holiday-free? (and (some #(= :excluded (nth % 5))
                                             bs)
                                       (not-any? #(= :only (nth % 5))
                                                 bs))]]
          [k (str (str/join group-sep
                            (for [{:keys [days hours]} merged]
                              (str hours " " (day-words days))))
                  (when holiday-free?
                    holiday-free))])))
