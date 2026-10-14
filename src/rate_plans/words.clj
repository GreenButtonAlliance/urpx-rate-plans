;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.words
  "Numbers, lists and dates in words. Knows nothing about any utility."
  (:require [clojure.string :as str]))

(def ^:private small-numbers
  ["zero" "one" "two" "three" "four" "five" "six" "seven" "eight" "nine" "ten"
   "eleven" "twelve" "thirteen" "fourteen" "fifteen" "sixteen" "seventeen"
   "eighteen" "nineteen" "twenty"])

(defn number
  "18 -> \"eighteen\", for 0 through 20."
  [n]
  (or (get small-numbers n)
      (throw (ex-info (str "No words for " n)
                      {:n n}))))

(defn and-list
  "[\"a\" \"b\" \"c\"] -> \"a, b and c\"."
  [xs]
  (if (next xs)
    (str (str/join ", " (butlast xs))
         " and "
         (last xs))
    (first xs)))

(def ^:private months
  ["January" "February" "March" "April" "May" "June" "July" "August"
   "September" "October" "November" "December"])

(defn long-date
  "\"2026-01-01\" -> \"January 1, 2026\"."
  [d]
  (let [[y m dd] (map parse-long (str/split d #"-"))]
    (str (months (dec m))
         " "
         dd
         ", "
         y)))
