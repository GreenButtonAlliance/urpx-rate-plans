;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.prose
  "Prose the source loads rather than holds: Markdown files beside a
   namespace, named by key, and the deferrals in the tariff.toml of the
   filing being generated. While the generator expands a document, each file
   read is recorded in `*reads*`. Knows nothing about any utility."
  (:require [clojure.java.io :as io]
            [clojure.string :as str])
  (:import (org.tomlj Toml TomlParseResult)))

(def ^:dynamic *reads*
  "An atom holding the set of repository paths read, or nil."
  nil)

(def ^:dynamic *filing*
  "The directory of the filing being generated, relative to the repository."
  nil)

(defn- read! [path]
  (when *reads*
    (swap! *reads* conj path))
  (slurp path))

(defn path
  "The file of prose key `k`, a keyword qualified by the namespace whose
   prose it is:

     :rate-plans.us.ca.pge.e-tou-c/coverage-2026-03-01
     -> src/rate_plans/us/ca/pge/prose/e-tou-c/coverage-2026-03-01.md"
  [k]
  (let [segments (str/split (namespace k) #"\.")]
    (str/join "/"
              (concat ["src"]
                      (map #(str/replace % "-" "_")
                           (butlast segments))
                      ["prose"
                       (last segments)
                       (str (name k) ".md")]))))

(defn- paragraphs
  "The paragraphs of Markdown `s`, separated by blank lines; refuses a
   paragraph broken across lines."
  [path s]
  (let [ps (str/split (str/trim s) #"\n[ \t]*\n")]
    (doseq [p ps
            :when (str/includes? p "\n")]
      (throw (ex-info (str path ": a paragraph spans more than one line")
                      {:path path
                       :paragraph p})))
    ps))

(defn text
  "The prose of key `k` (see `path`): its file's paragraphs joined by one
   space."
  [k]
  (let [p (path k)]
    (when-not (.isFile (io/file p))
      (throw (ex-info (str "No prose file " p " for " k)
                      {:key k
                       :path p})))
    (str/join " " (paragraphs p (read! p)))))

(defn dated
  "The prose of key `<k>-<date>`, or nil when that file does not exist."
  [k date]
  (let [k (keyword (namespace k) (str (name k) "-" date))]
    (when (.isFile (io/file (path k)))
      (text k))))

(defn- normalize
  "Runs of whitespace as one space, as a TOML string wrapped across lines
   reads in prose."
  [s]
  (str/join " " (str/split (str/trim s) #"\s+")))

(defn deferrals
  "The [modeling].deferrals of the filing being generated, each
   whitespace-normalized. Refuses unless every string in `cites` appears in
   them, so a figure the prose cites stays the one its table gives."
  [cites]
  (when-not *filing*
    (throw (ex-info "No filing is being generated" {})))
  (let [p (str *filing* "/tariff.toml")
        ^TomlParseResult toml (Toml/parse ^String (read! p))
        _ (when (.hasErrors toml)
            (throw (ex-info (str p ": " (first (.errors toml)))
                            {:path p})))
        ds (mapv normalize
                 (some-> (.getArray toml "modeling.deferrals")
                         .toList))
        all (str/join " " ds)
        missing (remove #(str/includes? all %) cites)]
    (when (seq missing)
      (throw (ex-info (str p ": [modeling].deferrals do not cite "
                           (str/join ", " (map pr-str missing)))
                      {:path p
                       :missing missing})))
    ds))

(defn deferral-coverage
  "A coverage evaluation listing the filing's deferrals (see `deferrals`) in
   the same words."
  [cites]
  (let [ds (deferrals cites)]
    (str "This filing does not carry everything its source document states. "
         (count ds)
         " parts are deferred, listed here in the same words as the filing's tariff.toml [modeling].deferrals so the two records cannot drift. "
         (str/join " "
                   (map-indexed (fn [i d]
                                  (str "(" (inc i) ") " d))
                                ds)))))
