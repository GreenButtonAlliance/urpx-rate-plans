;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: CDLA-Permissive-2.0
(ns dsl-fixture.bad-brackets
  (:require [rate-plans.defs]
            [urpx.defs :refer [defurpx]]))

(defurpx :rate-plans.kind/tou-brackets residential-tou-brackets
  {"2024-01-01"
   [[:peak      "mon-sat"       :mon-sat  "17:00" "21:00" :excluded]
    [:mid-peak  "mon-sat-day"   :mon-sun  "06:00" "17:00" :excluded]
    [:mid-peak  "mon-sat-late"  :mon-sat  "21:00" "25:00" :excluded]
    [:off-peak  "every-day"     :all      "00:00" "06:00"]]})
