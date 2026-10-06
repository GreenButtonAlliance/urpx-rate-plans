;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: CDLA-Permissive-2.0
(ns urpx-rate-plans
  "This corpus's walker for Clojure and babashka, one file for both.

  The layout is declared once, in corpus.json at the repository root, and read
  from there: roots, the include globs of each kind, and which kinds are the
  documents. dev/corpus.py and dev/corpus.sh read the same file, and
  dev/check_walkers.py fails the gate if any two disagree.

  clj-urpx's dev/corpus_sweep.clj resolves `sources` from whatever namespace
  `--layout` names, so this one plugs in with `--layout urpx-rate-plans`.

  As a program (`clojure -M -m urpx-rate-plans`, `bb -cp dev -m urpx-rate-plans`)
  it prints repo-relative paths: the documents with no arguments, the named
  kinds otherwise, and every kind as kind<TAB>path with --all."
  (:require [clojure.java.io :as io]
            [clojure.string :as str])
  (:import [java.io File]
           [java.nio.file FileSystems Path]))

(defn layout
  "corpus.json under `root`, with string keys."
  [root]
  (let [s (slurp (io/file root "corpus.json"))]
    (if (System/getProperty "babashka.version")
      ((requiring-resolve 'cheshire.core/parse-string) s)
      ((requiring-resolve 'clojure.data.json/read-str) s))))

(defn- rel
  "`f` as a POSIX path relative to `dir`."
  [^File dir ^File f]
  (str/replace (str (.relativize (.toPath dir) (.toPath f))) File/separator "/"))

(defn paths
  "Repo-relative paths of every file of `kinds` (default: the documents),
   sorted."
  ([root] (paths root nil))
  ([root kinds]
   (let [{:strs [roots documents] :as lay} (layout root)
         patterns (mapcat #(get-in lay ["kinds" % "include"]) (or (seq kinds) documents))
         fs       (FileSystems/getDefault)
         matchers (mapv #(.getPathMatcher fs (str "glob:" %)) patterns)
         top      (io/file root)]
     (->> roots
          (mapcat (fn [r]
                    (let [dir (io/file root r)]
                      (for [^File f (file-seq dir)
                            :when (.isFile f)
                            :let [p (.getPath fs (rel dir f) (make-array String 0))]
                            :when (some #(.matches ^java.nio.file.PathMatcher % ^Path p) matchers)]
                        (rel top f)))))
          distinct
          sort
          vec))))

(defn sources
  "Every corpus document under `root`, as Files, sorted."
  [root]
  (mapv #(io/file root %) (paths root)))

(defn withheld-dirs
  "The schedule directories dev/withheld-filings.json withholds from
   resolution, repo-relative with a trailing slash. dev/withheld_filings.py
   reads the same file and refuses once the pinned clj-urpx makes an entry
   stale."
  [root]
  (let [f (io/file root "dev" "withheld-filings.json")]
    (if-not (.exists f)
      []
      (let [s (slurp f)
            m (if (System/getProperty "babashka.version")
                ((requiring-resolve 'cheshire.core/parse-string) s)
                ((requiring-resolve 'clojure.data.json/read-str) s))]
        (mapv #(get % "schedule_dir") (get m "withheld"))))))

(defn withheld?
  "True when the repo-relative `path` lies under a withheld schedule directory."
  [root path]
  (boolean (some #(str/starts-with? path %) (withheld-dirs root))))

(defn -main [& args]
  (let [lines (if (= args ["--all"])
                (for [k (keys (get (layout ".") "kinds"))
                      p (paths "." [k])]
                  (str k "\t" p))
                (paths "." args))]
    (doseq [l (sort lines)] (println l))))
