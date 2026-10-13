;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
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
     out of window    the resolution carries
                      :urpx.resolved/outside-version-window: the filing's own
                      urpx:effectiveDateTime is after the probe instant, or its
                      urpx:expirationDateTime is before it, and clj-urpx
                      returns no ledgers. dev/validate_v020.clj admits the same
                      case as a refusal.

   Anything else fails, and so does a refusal. clj-urpx refuses by throwing
   an ex-info whose ex-data names a :reason (:urpx.price/no-tou-period,
   :urpx.price/no-version and the rest); the filing is then reported under
   that reason, with the plan, version and instant the ex-data names. Any
   other exception, including an ex-info with no :reason, propagates.

   The declared set comes from the COERCED plan rather
   than the raw JSON-LD, which is what confines it to the base plan's own
   ledgers: a filing that inlines its modifiers carries their ledgers too, and
   those belong to the composition path, not to this one.

   SCOPE LIMIT, stated rather than hidden: this covers base-plan resolution
   only. Modifier composition is exercised by dev/validate_v020.clj but its
   ledger coverage is not checked here.

   Exit: 0 clean, 1 unexplained absence, 3 refused.

   Usage: clojure -M:coverage"
  (:require [clojure.string :as str]
            [clojure.walk :as walk]
            [urpx.core :as core]
            [urpx.coerce :as coerce]
            [urpx.price :as price]
            [urpx-rate-plans :as layout])
  (:import [java.time ZoneId ZonedDateTime]))

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
  (layout/paths "." ["rate-plan"]))

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

;; Ex-data keys that say what a refusal was about, in the order printed.
(def ^:private refusal-subject-keys
  [:plan-id :version-id])

(defn refusal-cause
  "One line naming a clj-urpx refusal: its :reason, the plan and version its
   ex-data names, and the instant, which is ex-data's :at when present and
   `instant` otherwise."
  [data instant]
  (let [subject (for [k refusal-subject-keys
                      :let [v (get data k)]
                      :when (some? v)]
                  (str (name k) " " v))
        parts   (concat subject
                        [(str "at " (get data :at instant))])]
    (str "refused " (:reason data) " (" (str/join ", " parts) ")")))

(defn resolve-or-refusal
  "{:resolved r} for a resolution of `plan` at `instant`, or {:refusal cause}
   when clj-urpx refuses with an ex-info carrying a :reason. Any other
   exception propagates."
  [plan instant]
  (try
    {:resolved (price/resolve-prices plan instant)}
    (catch clojure.lang.ExceptionInfo e
      (let [data (ex-data e)]
        (if (contains? data :reason)
          {:refusal (refusal-cause data instant)}
          (throw e))))))

(defn -main [& _]
  (let [paths (base-plan-filings)]
    (when (empty? paths)
      (println "REFUSED: no base-plan filings under us/. The tree moved and this")
      (println "         gate was not updated. Refusing to report 0/0 as success.")
      (System/exit 3))
    (let [results  (for [path paths
                         :let [plan (-> path core/load-rate-plan coerce/coerce-rate-plan)]]
                     (merge {:file (last (str/split path #"/"))
                             :plan plan}
                            (resolve-or-refusal plan probe-instant)))
          refused  (filter :refusal results)
          rows     (for [{:keys [file plan resolved]} (remove :refusal results)
                         :let [got (set (keep :urpx.resolved/ledger-id
                                              (:urpx.resolved/ledgers resolved)))]
                         lid (sort (remove got (declared-ledgers plan)))]
                     {:file file
                      :ledger lid
                      :reason (if (:urpx.resolved/outside-version-window resolved)
                                "out of window (the version is not in force at the probe instant)"
                                (classify plan lid))})
          total-declared (reduce + (map #(-> % core/load-rate-plan coerce/coerce-rate-plan
                                             declared-ledgers count)
                                        paths))
          bad (filter #(nil? (:reason %)) rows)]
      (when (zero? total-declared)
        (println "REFUSED: the corpus declares no ledgers at all, so this gate")
        (println "         would pass vacuously.")
        (System/exit 3))
      (if (and (empty? bad) (empty? refused))
        (do (println (format "resolution coverage: clean (%d ledgers across %d base plans, %d explained absences)"
                             total-declared (count paths) (count rows)))
            (System/exit 0))
        (do (when (seq refused)
              (println (format "resolution coverage: %d base plan(s) refused by clj-urpx\n"
                               (count refused)))
              (doseq [{:keys [file refusal]} refused]
                (println (format "  %s\n      %s" refusal file)))
              (println))
            (when (seq bad)
              (println (format "resolution coverage: %d ledger(s) declared but absent from resolution, with no recognised reason\n"
                               (count bad)))
              (doseq [{:keys [file ledger]} bad]
                (println (format "  %s\n      %s" ledger file)))
              (println "\nA declared ledger that never comes back means the charge is invisible to")
              (println "every consumer while both gates stay green. See the header of this file."))
            (System/exit 1))))))
