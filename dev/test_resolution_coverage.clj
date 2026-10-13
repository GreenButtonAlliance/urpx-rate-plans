;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns test-resolution-coverage
  "How dev/lint_resolution_coverage.clj treats an exception from
   urpx.price/resolve-prices: a clj-urpx refusal (an ex-info with a :reason)
   becomes a cause naming that reason, and anything else propagates.

     clojure -M -m test-resolution-coverage

   Exit 0 every check passed, 1 otherwise."
  (:require [lint-resolution-coverage :as lint]
            [urpx.price :as price])
  (:import [java.time ZoneId ZonedDateTime]))

(def ^:private failures (atom []))

(def ^:private instant
  (ZonedDateTime/of 2026 7 15 17 0 0 0 (ZoneId/of "America/Los_Angeles")))

(defn- check
  [label ok detail]
  (println (str "  " (if ok "PASS" "FAIL") "  " label (when-not ok (str "  " detail))))
  (when-not ok
    (swap! failures conj label)))

(defn- outcome
  "resolve-or-refusal with resolve-prices throwing `e`, or the exception that
   escaped it as {:thrown e}."
  [e]
  (with-redefs [price/resolve-prices (fn [_ _] (throw e))]
    (try
      (lint/resolve-or-refusal {} instant)
      (catch Throwable t
        {:thrown t}))))

(defn -main [& _]
  (let [r (outcome (ex-info "no period"
                            {:reason     :urpx.price/no-tou-period
                             :plan-id    "smud:tod-5-8pm"
                             :version-id "smud:tod-5-8pm-2026-01-01"
                             :at         "2026-07-15T17:00-07:00"}))]
    (check "a refusal reports its reason, plan, version and instant"
           (= (:refusal r)
              (str "refused :urpx.price/no-tou-period (plan-id smud:tod-5-8pm, "
                   "version-id smud:tod-5-8pm-2026-01-01, at 2026-07-15T17:00-07:00)"))
           (pr-str r)))
  (let [r (outcome (ex-info "no version"
                            {:reason  :urpx.price/no-version
                             :plan-id "smud:tod-5-8pm"}))]
    (check "a refusal with no :at reports the probe instant"
           (= (:refusal r)
              (str "refused :urpx.price/no-version (plan-id smud:tod-5-8pm, at " instant ")"))
           (pr-str r)))
  (let [e (ex-info "no reason" {:plan-id "smud:tod-5-8pm"})]
    (check "an ex-info without :reason propagates"
           (identical? e (:thrown (outcome e)))
           (pr-str (outcome e))))
  (let [e (IllegalStateException. "a defect")]
    (check "an exception that is not an ex-info propagates"
           (identical? e (:thrown (outcome e)))
           (pr-str (outcome e))))
  (let [r (with-redefs [price/resolve-prices (fn [_ _] {:urpx.resolved/ledgers []})]
            (lint/resolve-or-refusal {} instant))]
    (check "a resolution comes back under :resolved"
           (= r {:resolved {:urpx.resolved/ledgers []}})
           (pr-str r)))
  (shutdown-agents)
  (System/exit (if (empty? @failures) 0 1)))
