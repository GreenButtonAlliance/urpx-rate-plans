;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: CDLA-Permissive-2.0
(ns dsl-fixture.bad-rates
  (:require [rate-plans.defs]
            [urpx.defs :refer [defurpx]]))

(defurpx :rate-plans.kind/rates rtc-rates
  {"2026-01-01" {:base-service-charge 39.45M :peak 16.10M :mid-peak 14.09M :off-peak 8.05M}
   "2027-01-01" {:base-service-charge 55.18M :peak 16.9 :mid-peak "14.79" :off-peak 8.45M}
   "2028-1-1"   {:base-service-charge 77.22M :peak 17.38M :mid-peak 15.21M :off-peak 8.69M}})
