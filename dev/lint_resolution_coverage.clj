;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: CDLA-Permissive-2.0
(ns lint-resolution-coverage
  "Require that every ledger a base plan declares actually comes back from
   resolution, or is absent for a reason this file recognises.

   WHY THIS EXISTS. dev/validate_v020.clj asks whether resolution SUCCEEDS.
   It never asked whether the charges a filing declares actually APPEAR, so a
   consumer-side regression that drops a whole class of charge left it green.
   That is not hypothetical: clj-urpx once excluded every PriceDefinition
   carrying a urpx:CalculationMethod from the base-plan path, which silently
   removed 89 recurring charges across all 40 base plans (every fixed,
   customer and base-services charge in the corpus). Composing SCE Schedule D
   with SCE CARE then returned two CARE discounts ON the Base Services Charge
   while the Base Services Charge itself was missing. Both gates passed.

   WHAT IS CHECKED. Ledgers, not prices. A single probe instant legitimately
   hides most individual prices (winter PriceDefinitions in July, off-peak at
   5pm), so per-price coverage at one instant is noise. A whole ledger going
   missing is not noise, and it is the shape the recurring-charge bug took.

   WHAT COUNTS AS A LEGITIMATE ABSENCE. Two classes, both structural:

     needs-selection  Every Price reaching this ledger sits under
                      urpx:hasPriceSetAlternatives, so resolution cannot pick
                      one without a caller-supplied :profile-alternatives
                      choice. PG&E's income-tiered Base Services Charge and
                      the Vintage PCIA ledgers are this shape.
     gated            A PriceDefinition on the ledger carries
                      urpx:hasApplicabilityRule, so a month or season gate can
                      correctly exclude it at the probe instant. The
                      California Climate Credit (April and October) is this.

   Anything else fails. The declared set comes from the COERCED plan rather
   than the raw JSON-LD, which is what confines it to the base plan's own
   ledgers: a filing that inlines its modifiers carries their ledgers too, and
   those belong to the composition path, not to this one.

   SCOPE LIMIT, stated rather than hidden: this covers base-plan resolution
   only. Modifier composition is exercised by dev/validate_v020.clj but its
   ledger coverage is not checked here.

   Exit: 0 clean, 1 unexplained absence, 3 refused.

   Usage: clojure -M:coverage"
  (:require [clojure.java.io :as io]
            [clojure.string :as str]
            [clojure.walk :as walk]
            [urpx.core :as core]
            [urpx.coerce :as coerce]
            [urpx.price :as price])
  (:import [java.io File]
           [java.time ZoneId ZonedDateTime]))

(def la (ZoneId/of "America/Los_Angeles"))

;; Same instant dev/validate_v020.clj probes, so the two gates agree on what
;; "now" means and a discrepancy between them is a real one.
(def probe-instant (ZonedDateTime/of 2026 7 15 17 0 0 0 la))

(defn- nodes-where
  "Every map in `root` satisfying `pred`."
  [root pred]
  (let [acc (atom [])]
    (walk/postwalk (fn [n] (when (and (map? n) (pred n)) (swap! acc conj n)) n) root)
    @acc))

(defn- base-plan-filings []
  (->> (file-seq (io/file "us"))
       (filter #(.isFile ^File %))
       (map #(.getPath ^File %))
       (filter #(re-matches #"us/.*/versions/[^/]+/rate-plan_.+\.jsonld" %))
       sort))

(defn- declared-ledgers
  "Ledger ids the coerced plan declares. A Ledger is identified by carrying
   both a ledgerType and a name, which distinguishes the definition from the
   bare {@id} references that point at it."
  [plan]
  (set (keep :jsonld/id (nodes-where plan #(and (:urpx/ledgerType %) (:urpx/name %))))))

(defn- ref-id
  "Id out of a Ref, which coercion leaves as a bare map in some positions and
   a vector of maps in others."
  [x]
  (cond (map? x) (:jsonld/id x)
        (sequential? x) (some ref-id x)))

(defn- pds-by-ledger [plan]
  (group-by #(ref-id (:urpx/referencesLedger %))
            (nodes-where plan :urpx/referencesLedger)))

(defn- alternative-price-ids
  "Ids of Prices reachable only through urpx:hasPriceSetAlternatives.

   Walks the VALUE of that property, not the node carrying it: hasPrice,
   hasPriceSet and hasPriceSetAlternatives are siblings on one Prices node, so
   searching the parent would sweep the flat prices in with the alternatives
   and mark the whole filing as needing a selection."
  [plan]
  (set (keep :jsonld/id
             (mapcat #(nodes-where (:urpx/hasPriceSetAlternatives %)
                                   :urpx/referencesPriceDefinition)
                     (nodes-where plan :urpx/hasPriceSetAlternatives)))))

(defn- flat-prices-by-pd
  "Prices that reach their PriceDefinition WITHOUT a PriceSetAlternative in
   between, grouped by the PriceDefinition they reference."
  [plan]
  (let [alts (alternative-price-ids plan)]
    (->> (nodes-where plan :urpx/referencesPriceDefinition)
         (remove #(alts (:jsonld/id %)))
         (group-by #(ref-id (:urpx/referencesPriceDefinition %))))))

(defn- classify
  "Why is `ledger-id` absent from resolution? nil means no legitimate reason."
  [plan ledger-id]
  (let [lpds (get (pds-by-ledger plan) ledger-id)
        flat (flat-prices-by-pd plan)]
    (cond
      (empty? lpds) nil
      (every? #(empty? (get flat (:jsonld/id %))) lpds)
      "needs-selection (every price sits under hasPriceSetAlternatives)"
      (some :urpx/hasApplicabilityRule lpds)
      "gated (a PriceDefinition carries an applicability rule)"
      :else nil)))

(defn -main [& _]
  (let [paths (base-plan-filings)]
    (when (empty? paths)
      (println "REFUSED: no base-plan filings under us/. The tree moved and this")
      (println "         gate was not updated. Refusing to report 0/0 as success.")
      (System/exit 3))
    (let [rows (for [path paths
                     :let [plan (-> path core/load-rate-plan coerce/coerce-rate-plan)
                           decl (declared-ledgers plan)
                           got  (set (keep :urpx.resolved/ledger-id
                                           (:urpx.resolved/ledgers
                                            (try (price/resolve-prices plan probe-instant)
                                                 (catch Exception _ nil)))))]
                     lid  (sort (remove got decl))]
                 {:file (last (str/split path #"/"))
                  :ledger lid
                  :reason (classify plan lid)})
          total-declared (reduce + (map #(-> % core/load-rate-plan coerce/coerce-rate-plan
                                             declared-ledgers count)
                                        paths))
          bad (filter #(nil? (:reason %)) rows)]
      (when (zero? total-declared)
        (println "REFUSED: the corpus declares no ledgers at all, so this gate")
        (println "         would pass vacuously.")
        (System/exit 3))
      (if (empty? bad)
        (do (println (format "resolution coverage: clean (%d ledgers across %d base plans, %d explained absences)"
                             total-declared (count paths) (count rows)))
            (System/exit 0))
        (do (println (format "resolution coverage: %d ledger(s) declared but absent from resolution, with no recognised reason\n"
                             (count bad)))
            (doseq [{:keys [file ledger]} bad]
              (println (format "  %s\n      %s" ledger file)))
            (println "\nA declared ledger that never comes back means the charge is invisible to")
            (println "every consumer while both gates stay green. See the header of this file.")
            (System/exit 1))))))
