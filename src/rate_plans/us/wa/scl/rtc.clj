;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.us.wa.scl.rtc
  "Seattle City Light Schedule RTC, Residential: City Time-of-Use."
  (:require [rate-plans.defs]
            [rate-plans.us.wa.scl.common :as scl]
            [urpx.defs :refer [defurpx]]))

(defurpx :rate-plans.kind/rates rtc-rates
  "SMC 21.49.030.B as amended by Ordinance 127473, page 11; cents per meter
   per day (base) and per kWh, one entry per column 'Effective January 1, <year>'."
  {"2026-01-01" {:base-service-charge 39.45M :peak 16.10M :mid-peak 14.09M :off-peak 8.05M}
   "2027-01-01" {:base-service-charge 55.18M :peak 16.90M :mid-peak 14.79M :off-peak 8.45M}
   "2028-01-01" {:base-service-charge 77.22M :peak 17.38M :mid-peak 15.21M :off-peak 8.69M}})

(defurpx :rate-plans.kind/document rtc
  {:kind :rate-plan
   :utility scl/scl
   :schedule "rtc"
   :identifier "RTC"
   :name "Residential: City Time-of-Use"
   :where "inside the City of Seattle"
   :initial-effective-date "2024-01-01"
   :customer-choice :urpx/voluntaryChoice
   :default? false
   :versions rtc-rates
   :expand scl/residential-tou-plan})
