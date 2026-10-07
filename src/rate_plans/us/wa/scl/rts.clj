;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: CDLA-Permissive-2.0
(ns rate-plans.us.wa.scl.rts
  "Seattle City Light Schedule RTS, Residential: Suburban Time-of-Use."
  (:require [rate-plans.defs]
            [rate-plans.us.wa.scl.common :as scl]
            [urpx.defs :refer [defurpx]]))

(defurpx :rate-plans.kind/rates rts-rates
  "SMC 21.49.030.B as amended by Ordinance 127473, page 11; cents per meter
   per day (base) and per kWh, one entry per column 'Effective January 1, <year>'."
  {"2026-01-01" {:base-service-charge 39.45M :peak 16.32M :mid-peak 14.28M :off-peak 8.16M}
   "2027-01-01" {:base-service-charge 55.18M :peak 17.02M :mid-peak 14.89M :off-peak 8.51M}
   "2028-01-01" {:base-service-charge 77.22M :peak 17.86M :mid-peak 15.63M :off-peak 8.93M}})

(defurpx :rate-plans.kind/document rts
  {:kind :rate-plan
   :utility scl/scl
   :schedule "rts"
   :identifier "RTS"
   :name "Residential: Suburban Time-of-Use"
   :where "in the suburban jurisdictions City Light serves"
   :initial-effective-date "2024-01-01"
   :customer-choice :urpx/voluntaryChoice
   :default? false
   :price-summary
   (str "Energy subtotal for RTS: its Peak, Mid-Peak and Off-Peak energy charges. "
        "SMC 21.49.030.A: \"All charges in Schedule RSS shall be increased by the following percentages respective of the location of service\", applied to RTS by 21.49.030.B. "
        "scl:residential-suburban takes its percentage of this subtotal, and separately of the Base Service Charge.")
   :versions rts-rates
   :expand scl/residential-tou-plan})
