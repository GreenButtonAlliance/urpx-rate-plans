;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns test-dsl-validation
  "Each fixture under dev/fixtures/dsl/ holds one invalid definition, and
   loading it must fail with an error naming the fixture's file and line and
   every bad value in it.

     clojure -M -m test-dsl-validation

   Exit 0 every fixture failed as expected, 1 otherwise."
  (:require [clojure.string :as str]))

(def cases
  [{:file "dev/fixtures/dsl/bad_rates.clj"
    :expect ["Invalid :rate-plans.kind/rates dsl-fixture.bad-rates/rtc-rates"
             "bad_rates.clj:7"
             "at [\"2027-01-01\" :peak]: 16.9 should be a BigDecimal with 2 decimal places"
             "at [\"2027-01-01\" :mid-peak]: \"14.79\" should be a BigDecimal with 2 decimal places"
             "at [\"2028-1-1\"]: \"2028-1-1\" should be a yyyy-mm-dd string"]}
   {:file "dev/fixtures/dsl/bad_brackets.clj"
    :expect ["Invalid :rate-plans.kind/tou-brackets dsl-fixture.bad-brackets/residential-tou-brackets"
             "bad_brackets.clj:7"
             "at [\"2024-01-01\" 1 2]: :mon-sun should be either"
             "at [\"2024-01-01\" 2 4]: \"25:00\" should be an hh:mm string"
             "at [\"2024-01-01\" 3]:"
             "invalid tuple size 5, expected 6"]}
   {:file "dev/fixtures/dsl/bad_builder_key.clj"
    :expect ["bad_builder_key.clj:7"
             "urpx:Holiday refuses unknown keys [:holiday-rul]"]}])

(defn- messages
  "Every message in the cause chain of `e`, one per line."
  [e]
  (->> e
       (iterate ex-cause)
       (take-while some?)
       (map ex-message)
       (str/join "\n")))

(defn- run-case [{:keys [file expect]}]
  (let [msg (try
              (load-file file)
              nil
              (catch Exception e
                (messages e)))
        missing (when msg
                  (remove #(str/includes? msg %) expect))]
    (cond
      (nil? msg)
      (do (println "  FAIL " file "loaded without an error")
          false)

      (seq missing)
      (do (println "  FAIL " file "error does not state:")
          (run! #(println "         " %) missing)
          (println "        error was:" msg)
          false)

      :else
      (do (println "  PASS " file)
          true))))

(defn -main []
  (let [results (mapv run-case cases)
        failed (count (remove true? results))]
    (println (str (- (count cases) failed)
                  " of "
                  (count cases)
                  " invalid fixtures refused with a located error"))
    (shutdown-agents)
    (System/exit (if (zero? failed) 0 1))))
