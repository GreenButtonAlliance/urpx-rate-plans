;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns test-shacl-gate
  "Negative fixtures for dev/shacl_gate.clj: version dispatch, and the shape
   exceptions in dev/shape-exceptions.json.

   Dispatch fails silently when it picks the wrong shapes: nothing is
   targeted, validation conforms trivially, and the run reports success. So a
   misdispatch must refuse, never pass.

   An exception fails by dropping too much: a result the proposal would NOT
   remove disappears too, and the gate goes quiet on a real defect. So most
   exception cases are negatives, data the proposal itself rejects or that has
   nothing to do with it, which must still fail. Each fixture is validated
   against the v0.5.1 shapes with the ontology mixed in, and the exceptions are
   applied to its results.

   Run: clojure -M -m test-shacl-gate (exit 1 when an assertion fails)."
  (:require [clojure.java.io :as io]
            [clojure.string :as str]
            [shacl-gate :as gate]
            [shacl.core :as shacl])
  (:import (org.apache.jena.graph Graph GraphMemFactory GraphUtil NodeFactory Triple)))

(def ^:private failures (atom []))

(defn- check
  [label ok detail]
  (println (str "  " (if ok "PASS" "FAIL") "  " label (when-not ok (str "  " detail))))
  (when-not ok
    (swap! failures conj label)))

;; ---------------------------------------------------------------------------
;; Dispatch
;; ---------------------------------------------------------------------------

(defn- status
  "Validate `files`, optionally FORCING a revision to simulate misdispatch."
  [ctx exceptions files rev]
  (:status (binding [*err* (java.io.StringWriter.)]
             (gate/validate-files ctx files "test" {:verbose? false
                                                    :rev-override rev
                                                    :exceptions exceptions}))))

(defn- dispatch-cases
  [ctx exceptions]
  (println "Version-dispatch negative fixtures\n")
  (let [fx #(io/file (:root ctx) "dev" "fixtures" %)
        ;; Hand-authored, NOT live corpus files: a fixture must not move under
        ;; its own test.
        v021-good (fx "v021-conforming.jsonld")
        v051-good (fx "v051-conforming.jsonld")
        v051-bad (fx "v051-missing-required.jsonld")
        run (fn [label files rev want]
              (let [got (status ctx exceptions files rev)]
                (check label (= want got) (str "got " got ", want " want))))]
    (run "v0.5.1 fixture, dispatched" [v051-good] nil :ok)
    ;; What matters for v0.2.1 is that the file is TARGETED rather than
    ;; refused, which proves dispatch selected the right shapes.
    (run "v0.2.1 fixture, dispatched and targeted" [v021-good] nil :violations)
    (run "v0.5.1 fixture missing urpx:name" [v051-bad] nil :violations)
    (run "v0.5.1 file forced onto v0.2.1 shapes" [v051-good] "v0.2.1" :refused)
    (run "v0.2.1 fixture forced onto v0.5.1 shapes" [v021-good] "v0.5.1" :refused)
    (run "mixed-vocabulary set" [v021-good v051-good] nil :refused)))

;; ---------------------------------------------------------------------------
;; Shape exceptions
;; ---------------------------------------------------------------------------

(def ^:private prefix
  "@prefix urpx: <https://urpx.org/ns/ontology/> .
   @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
   @prefix ex: <https://example.org/> .
   ")

;; A rate plan's ladder tier, the target every adjusting bracket below names.
(def ^:private target
  "ex:target a urpx:ServiceTier ; urpx:serviceTierNumber 1 ;
     urpx:hasServiceBracket ex:target-b .
   ex:target-b a urpx:ServiceBracket ;
     urpx:lowerBound \"0\"^^xsd:decimal ;
     urpx:lowerBoundOperator urpx:greaterThanOrEqualOperator ;
     urpx:upperBound \"10.0\"^^xsd:decimal ;
     urpx:upperBoundOperator urpx:lessThanOrEqualOperator .
   ")

(defn- host
  "A modifier billing model hosting `brackets` (Turtle bodies) in one tier."
  [brackets & {:keys [tier-number?]}]
  (let [names (map #(str "ex:b" %) (range (count brackets)))]
    (str/join "\n"
              (concat ["ex:bm a urpx:BillingModel ; urpx:hasServiceTiers ex:sts ."
                       "ex:sts a urpx:ServiceTiers ; urpx:hasServiceTier ex:host ."
                       (str "ex:host a urpx:ServiceTier ; urpx:hasServiceBracket "
                            (str/join ", " names) " .")]
                      (when tier-number? ["ex:host urpx:serviceTierNumber 1 ."])
                      (map (fn [n body] (str n " a urpx:ServiceBracket ; " body " ."))
                           names
                           brackets)))))

(def ^:private adjust
  "urpx:adjustsServiceTier ex:target ; urpx:upperBoundOffset \"1.9\"^^xsd:decimal")

(def ^:private rev "v0.5.1")

(defn- run-ttl
  "[all keys, kept keys, removed counts] for a Turtle fixture."
  ([ctx exceptions ttl] (run-ttl ctx exceptions ttl ((:shapes-graph ctx) rev)))
  ([ctx exceptions ttl ^Graph shapes-graph]
   (let [data (shacl/read-turtle (.getBytes (str prefix ttl) "UTF-8"))
         ctx (assoc ctx
                    :shapes-graph (constantly shapes-graph)
                    :shapes (constantly (org.apache.jena.shacl.Shapes/parse shapes-graph)))
         {:keys [report kept removed]} (gate/validate-graph ctx rev data exceptions)]
     [(mapv gate/result-key (:results report)) (mapv gate/result-key kept) removed])))

(defn- short-keys
  [ks]
  (vec (sort (set (for [[f p c] ks]
                    [(last (str/split f #"/")) (last (str/split p #"/")) (last (str/split c #"#"))])))))

(defn- kept-on?
  [kept focus path comp]
  (boolean (some (fn [[f p c]]
                   (and (str/ends-with? f (str "/" focus))
                        (str/ends-with? p path)
                        (str/ends-with? c comp)))
                 kept)))

(defn- exception-cases
  [ctx exceptions]
  (println (str "\nShape exceptions, against URPX " rev "\n"))
  (let [run #(run-ttl ctx exceptions %)
        closed "ClosedConstraintComponent"
        min-count "MinCountConstraintComponent"]
    ;; Positive: what urpx-org/urpx#80 admits, and v0.5.1 rejects, is dropped whole.
    (let [[ks kept removed] (run (str target
                                      (host [adjust
                                             (str "urpx:adjustsServiceTier ex:target ; "
                                                  "urpx:lowerBoundOffset \"2.6\"^^xsd:decimal")])))]
      (check "v0.5.1 rejects an adjusting bracket (fixture is live)" (seq ks) (short-keys ks))
      (check "#80-conforming host: every result excepted"
             (and (empty? kept) (= (count ks) (get removed "BOUND_OFFSET_EXCEPTION")))
             (short-keys kept)))
    ;; Negative: a bound AND an offset. #80's fourth branch forbids bounds and
    ;; its other three forbid the new terms.
    (let [[_ kept] (run (str target
                             (host [(str adjust " ; urpx:lowerBound \"0\"^^xsd:decimal ; "
                                         "urpx:lowerBoundOperator urpx:greaterThanOrEqualOperator")])))]
      (check "bound plus offset keeps its closed-shape result"
             (kept-on? kept "b0" "adjustsServiceTier" closed) (short-keys kept)))
    ;; Negative: two targets (#80 sets sh:maxCount 1).
    (let [[_ kept] (run (str target
                             "ex:target2 a urpx:ServiceTier ; urpx:serviceTierNumber 2 ."
                             (host [(str adjust " ; urpx:adjustsServiceTier ex:target2")])))]
      (check "two targets are not excepted"
             (kept-on? kept "b0" "adjustsServiceTier" closed) (short-keys kept)))
    ;; Negative: a target that is itself a host (self-reference, #80's sh:node).
    (let [[_ kept] (run (host [(str "urpx:adjustsServiceTier ex:host ; "
                                    "urpx:upperBoundOffset \"1.9\"^^xsd:decimal")]))]
      (check "a bracket adjusting its own host is not excepted"
             (kept-on? kept "b0" "adjustsServiceTier" closed) (short-keys kept)))
    ;; Negative: an offset that is a string (#80 types offsets xsd:decimal).
    (let [[_ kept] (run (str target
                             (host ["urpx:adjustsServiceTier ex:target ; urpx:upperBoundOffset \"1.9\""])))]
      (check "a string offset is not excepted"
             (kept-on? kept "b0" "upperBoundOffset" closed) (short-keys kept)))
    ;; Negative: a numberless tier whose brackets are ordinary ones. #80 admits
    ;; a numberless tier only when every bracket in it adjusts.
    (let [[_ kept] (run (str target
                             "ex:plain a urpx:ServiceTier ; urpx:hasServiceBracket ex:plain-b ."
                             "ex:plain-b a urpx:ServiceBracket ; urpx:lowerBound \"0\"^^xsd:decimal ; "
                             "urpx:lowerBoundOperator urpx:greaterThanOrEqualOperator ."))]
      (check "a numberless tier with ordinary brackets keeps its minCount result"
             (kept-on? kept "plain" "serviceTierNumber" min-count) (short-keys kept)))
    ;; Negative: a billing model with no price definition and no adjusting bracket.
    (let [[_ kept] (run "ex:bm a urpx:BillingModel .")]
      (check "an empty billing model keeps its minCount result"
             (kept-on? kept "bm" "hasPriceDefinition" min-count) (short-keys kept)))
    ;; Negative: an unrelated closed-shape result on an adjusting bracket.
    (let [[_ kept] (run (str target (host [(str adjust " ; urpx:name \"x\"")])))]
      (check "an unrelated property on an adjusting bracket still fails"
             (kept-on? kept "b0" "name" closed) (short-keys kept)))
    ;; urpx-org/urpx#71: daysOfWeek is excepted on a TimeBracket only.
    (let [[_ kept removed] (run "ex:tb a urpx:TimeBracket ; urpx:daysOfWeek urpx:monday .")]
      (check "daysOfWeek on a TimeBracket is excepted"
             (and (not (kept-on? kept "tb" "daysOfWeek" closed))
                  (<= 1 (get removed "DAYS_OF_WEEK_EXCEPTION" 0)))
             (short-keys kept)))
    (let [[_ kept] (run (str target
                             "ex:sb a urpx:ServiceBracket ; urpx:daysOfWeek urpx:monday ; "
                             "urpx:lowerBound \"0\"^^xsd:decimal ; "
                             "urpx:lowerBoundOperator urpx:greaterThanOrEqualOperator ."))]
      (check "daysOfWeek on a ServiceBracket is not excepted"
             (kept-on? kept "sb" "daysOfWeek" closed) (short-keys kept)))
    ;; Switch-off: shapes that name an entry's terms make it drop nothing.
    (let [defining (doto (GraphMemFactory/createDefaultGraph)
                     (GraphUtil/addInto ^Graph ((:shapes-graph ctx) rev))
                     (.add (Triple/create (NodeFactory/createBlankNode)
                                          (NodeFactory/createURI "http://www.w3.org/ns/shacl#path")
                                          (NodeFactory/createURI
                                           "https://urpx.org/ns/ontology/adjustsServiceTier"))))
          [ks kept removed] (run-ttl ctx exceptions (str target (host [adjust])) defining)]
      (check "shapes defining #80's terms switch BOUND_OFFSET_EXCEPTION off"
             (and (not (contains? removed "BOUND_OFFSET_EXCEPTION")) (= kept ks) (seq ks))
             (str removed)))))

(defn -main
  [& _]
  (let [root (.getCanonicalFile (io/file (System/getProperty "user.dir")))
        ctx (gate/context root)
        exceptions (gate/shape-exceptions root)]
    (dispatch-cases ctx exceptions)
    (exception-cases ctx exceptions)
    (println)
    (if (seq @failures)
      (println (str (count @failures) " assertion(s) failed: " (str/join ", " @failures)))
      (println "all dispatch and shape-exception assertions hold"))
    (flush)
    (shutdown-agents)
    (System/exit (if (seq @failures) 1 0))))
