;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: CDLA-Permissive-2.0
(ns dsl-fixture.bad-builder-key
  (:require [urpx.dsl :as dsl]))

(def new-years-day
  (dsl/holiday
   {:holiday-name "New Year's Day"
    :holiday-rul "January 1"}))
