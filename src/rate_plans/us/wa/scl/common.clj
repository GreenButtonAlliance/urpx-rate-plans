;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.us.wa.scl.common
  "Seattle City Light: what its schedules share. Every table is keyed by the
   date it takes effect; a later filing adds a key."
  (:require [clojure.string :as str]
            [rate-plans.defs :refer [as-of]]
            [rate-plans.tou :as tou]
            [rate-plans.urpx :as u]
            [urpx.defs :refer [defurpx]]))

(defurpx :rate-plans.kind/utility scl
  {:key "scl"
   :legal-name "Seattle City Light"
   :eia-id "16868"
   :prefix ["scl" "https://rate-plans.grid-coordination.energy/scl/"]
   :timezone "America/Los_Angeles"
   :path ["us" "wa" "scl" "electricity"]})

(defurpx :rate-plans.kind/source ordinance
  "SMC 21.49.030 as amended; pages per schedule."
  {"2026-01-01" {:file "Ord_127473.pdf"
                 :url "https://clerk.seattle.gov/~archives/Ordinances/Ord_127473.pdf"
                 :retrieved "2026-10-05"
                 :evaluated-on "2026-10-05"
                 :pages {:rtc [10 12] :rts [10 12] :residential-suburban [9 11]}}})

(defurpx :rate-plans.kind/holidays holidays
  "City Light's residential Time of Use page: the NERC holidays; a Sunday one
   is observed the following Monday."
  {"2024-01-01"
   {:named
    ;; key                name                rule                           fixed date
    [[:new-years-day     "New Year's Day"    "January 1"                    [1 1]]
     [:memorial-day      "Memorial Day"      "Last Monday in May"           nil]
     [:independence-day  "Independence Day"  "July 4"                       [7 4]]
     [:labor-day         "Labor Day"         "First Monday in September"    nil]
     [:thanksgiving-day  "Thanksgiving Day"  "Fourth Thursday in November"  nil]
     [:christmas-day     "Christmas Day"     "December 25"                  [12 25]]]
    :observed-monday-after-sunday {:of [:new-years-day :independence-day :christmas-day]
                                   :through 2040}}})

(defurpx :rate-plans.kind/tou-periods residential-tou-periods
  {"2024-01-01"
   ;; key        label; row order gives tier and period numbers 1 to 3
   [[:peak      "Peak"]
    [:mid-peak  "Mid-Peak"]
    [:off-peak  "Off-Peak"]]})

(defurpx :rate-plans.kind/tou-brackets residential-tou-brackets
  {"2024-01-01"
   ;; period     bracket         days      start   end     holidays
   [[:peak      "mon-sat"       :mon-sat  "17:00" "21:00" :excluded]
    [:mid-peak  "mon-sat-day"   :mon-sat  "06:00" "17:00" :excluded]
    [:mid-peak  "mon-sat-late"  :mon-sat  "21:00" "24:00" :excluded]
    [:mid-peak  "sunday"        :sun      "06:00" "24:00" :excluded]
    [:mid-peak  "holiday"       :all      "06:00" "24:00" :only]
    [:off-peak  "every-day"     :all      "00:00" "06:00" nil]]})

(def hours-styles
  "How the prose words bracket hours: :sentence in version descriptions,
   :name in TOUPeriod names."
  {:sentence {:clock-fmt :long
              :range " to "
              :group-sep " and "
              :holiday-free ", other than on a holiday"
              :day-words {:all "every day"
                          :mon-sat "Mondays through Saturdays"
                          [:sun :holiday] "on Sundays and holidays"}}
   :name {:clock-fmt :compact
          :range "-"
          :group-sep "; "
          :holiday-free ", not on a holiday"
          :day-words {:all "every day"
                      :mon-sat "Mondays through Saturdays"
                      [:sun :holiday] "Sundays and holidays"}}})

;; ---------------------------------------------------------------------------
;; Residential suburban (RSS) multipliers and undergrounding charges
;; ---------------------------------------------------------------------------

(defurpx :rate-plans.kind/jurisdictions rss-jurisdictions
  ;; key                name                          in a sentence
  [[:burien            "Burien"                      "Burien"]
   [:king-county       "Unincorporated King County"  "unincorporated King County"]
   [:lake-forest-park  "Lake Forest Park"            "Lake Forest Park"]
   [:normandy-park     "Normandy Park"               "Normandy Park"]
   [:seatac            "SeaTac"                      "SeaTac"]
   [:shoreline         "Shoreline"                   "Shoreline"]
   [:tukwila           "Tukwila"                     "Tukwila"]])

(defurpx :rate-plans.kind/percentages rss-multipliers
  "SMC 21.49.030.A, 'RSS suburban franchise and tax multipliers', percent."
  {"2026-01-01" {:burien 8.00M :king-county 8.00M :seatac 8.00M :shoreline 8.00M
                 :tukwila 7.19M :lake-forest-park 8.04M :normandy-park 6.38M}
   "2027-01-01" {:burien 8.00M :king-county 8.00M :seatac 8.00M :shoreline 8.00M
                 :tukwila 7.05M :lake-forest-park 8.04M :normandy-park 6.38M}
   "2028-01-01" {:burien 8.00M :king-county 8.00M :seatac 8.00M :shoreline 8.00M
                 :tukwila 7.07M :lake-forest-park 8.04M :normandy-park 6.38M}})

(defurpx :rate-plans.kind/undergrounding rss-undergrounding
  "SMC 21.49.030.A, Suburban Undergrounding Charges, cents per kWh. The 2023
   column (struck) and the 2025 column carry the same values."
  (let [charges (array-map
                 :shoreline [[:north-city  "North City"  0.07M]
                             [:aurora-1    "Aurora 1"    0.17M]
                             [:aurora-2    "Aurora 2"    0.18M]
                             [:aurora-3a   "Aurora 3A"   0.05M]
                             [:aurora-3b   "Aurora 3B"   0.22M]]
                 :burien [[:first-avenue-south-1 "First Avenue South 1" 0.37M]
                          [:first-avenue-south-2 "First Avenue South 2" 0.13M]])]
    {"2023-01-01" charges
     "2025-01-01" charges}))

;; ---------------------------------------------------------------------------
;; Prose shared by RTC and RTS
;; ---------------------------------------------------------------------------

(defurpx :rate-plans.kind/description tou-prose
  {:version
   (str "Seattle City Light Schedule {identifier} ({name}), the optional residential time-of-use schedule for customers {where}, Seattle Municipal Code 21.49.030.B as amended by Ordinance 127473 (Council Bill 121231, passed July 21, 2026, approved July 22, 2026). "
        "This version carries the column headed 'Effective {effective}': {rates}. {hours}. There are no seasons and no blocks. "
        "The Monday-through-Saturday and Sunday brackets name their days with urpx:daysOfWeek, proposed in urpx-org/urpx#71 and in no URPX release yet.")
   :version-note
   {"2026-01-01" "The 2026 column was enacted by Ordinance 127122 and is restated unchanged by Ordinance 127473; City Light opened enrollment in the schedule on May 4, 2026."}
   :superseded "Superseded on {next} by the ordinance's next column."
   :eligibility-name "Eligibility for Schedule {identifier} ({name})"
   :eligibility
   "SMC 21.49.030.B as amended by Ordinance 127473: Schedules RTC and RTS are optional rate schedules available to customers who meet eligibility requirements outlined in City Light's Department Policy and Procedure (DPP) 500 P III-434, as amended, or successor rule. Customers may return to their default rate schedule but will not be able to re-enroll in Schedule RTC or RTS until 12 months from the time of unenrollment. City Light's residential Time of Use page requires an advanced meter and a Utility Services Website profile, and does not offer the rate to net metering customers. 21.49.030.C limits normal residential service to single-phase. The condition expression tests only that the customer is residential."
   :coverage
   (str "This filing does not carry everything its source document states. 1 parts are deferred, listed here in the same words as the filing's tariff.toml [modeling].deferrals so the two records cannot drift. "
        "(1) City Light's residential Time of Use page: a NERC holiday that falls on a Sunday \"is observed on the following Monday\"; one on a Saturday \"remains on that Saturday\". New Year's Day, Independence Day and Christmas Day in {holidays-id} carry no urpx:observanceRule, so each resolves on its actual date and a Saturday one stays on Saturday. "
        "The Monday after a Sunday New Year's Day, Independence Day or Christmas Day is carried as a dated urpx:Holiday with urpx:holidayDate: {observed}. After {through} each such Sunday holiday needs a further dated entry, until urpx:mondayIfSundayObservance (proposed in urpx-org/urpx#77) can state the rule; the dated entries then come out.")})

(defn- rates-sentence [periods rates]
  (str "Base Service Charge "
       (u/plain (:base-service-charge rates))
       " cents per meter per day; Energy "
       (u/and-list (for [[k label] (reverse periods)]
                     (str label
                          " "
                          (u/plain (rates k)))))
       " cents per kWh"))

(defn- coverage-description
  [coverage calendar p schedule date]
  (let [year (parse-long (subs date 0 4))
        observed (->> (tou/observed-mondays calendar year)
                      (map last)
                      (str/join ", "))]
    (u/fill coverage
            {:holidays-id (str p ":" schedule "-" date "-holidays")
             :observed observed
             :through (get-in calendar
                              [:observed-monday-after-sunday :through])})))

(defn residential-tou-plan
  "Expand a residential TOU schedule (RTC, RTS) at version `date`."
  [{:keys [schedule versions] :as doc} date next]
  (let [rates (versions date)
        brackets (as-of residential-tou-brackets date)
        names (tou/hours-phrases brackets (:name hours-styles))
        sentence (tou/hours-phrases brackets (:sentence hours-styles))
        periods (mapv (fn [[k label]]
                        [k label (str label " (" (names k) ")")])
                      (as-of residential-tou-periods date))
        calendar (as-of holidays date)
        source (as-of ordinance date)
        [p] (:prefix scl)
        words (assoc doc
                     :effective (u/long-date date)
                     :next next
                     :rates (rates-sentence periods rates)
                     :hours (str/join "; "
                                      (for [[k label] (reverse periods)]
                                        (str label " is " (sentence k)))))
        {:keys [version version-note superseded eligibility-name eligibility coverage]} tou-prose]
    (tou/package
     (merge doc
            {:utility scl
             :version date
             :next next
             :rates rates
             :tou-periods periods
             :tou-brackets brackets
             :calendar calendar
             :source source
             :pages (get-in source [:pages (keyword schedule)])
             :description (cond-> (u/fill version words)
                            (version-note date) (str " " (version-note date))
                            next (str " " (u/fill superseded words)))
             :eligibility {:name (u/fill eligibility-name words)
                           :description eligibility
                           :customer-kind :urpx/residentialKind}
             :coverage {:result :urpx/partial
                        :description (coverage-description coverage
                                                           calendar
                                                           p
                                                           schedule
                                                           date)}}))))
