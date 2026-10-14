;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.us.wa.scl.residential-suburban
  "Seattle City Light's suburban franchise and tax multipliers and suburban
   undergrounding charges on Schedule RTS: a RatePlanModifier on scl:rts."
  (:require [clojure.string :as str]
            [rate-plans.alternatives :as alt]
            [rate-plans.defs :refer [as-of effective-key since]]
            [rate-plans.tou :as tou]
            [rate-plans.urpx :as u]
            [rate-plans.us.wa.scl.common :as scl]
            [rate-plans.us.wa.scl.rts :as rts]
            [rate-plans.words :as words]
            [urpx.defs :refer [defurpx]]))

(defurpx :rate-plans.kind/description prose
  {:version
   (str "Seattle City Light's suburban franchise and tax multipliers and suburban undergrounding charges on Schedule {base-identifier} ({base-name}). "
        "SMC 21.49.030.A, as amended by Ordinance 127473, states for Schedule RSS that 'All charges in Schedule RSS shall be increased by the following percentages respective of the location of service' and that 'Additional undergrounding charges will apply to all customers in Shoreline and Burien'; 21.49.030.B applies 'The same franchise and tax multipliers and suburban undergrounding charges ... to Schedule RTS as Schedule RSS.' "
        "This version carries the multiplier column headed 'Effective {effective}': {multipliers}. "
        "The undergrounding charges, unchanged since {per-kwh-since}, total {per-kwh}. "
        "The customer's jurisdiction is a urpx:ProfileAlternatives dimension. Each alternative applies its percentage twice, as a multiplier over the RTS version's energy subtotal, which holds its Peak, Mid-Peak and Off-Peak energy charges, and as a multiplier over its Base Service Charge. "
        "A customer in Renton takes Schedule RTS with no multiplier and no undergrounding charge, so takes it without this modifier.")
   :superseded "Superseded on {next} by the ordinance's next multiplier column."
   :eligibility-name "Residential customer on Schedule RTS in a suburban jurisdiction"
   :eligibility "SMC 21.49.030.B: the franchise and tax multipliers and suburban undergrounding charges of Schedule RSS apply to Schedule RTS. Which multiplier and which undergrounding charges apply is set by the location of service and is the urpx:ProfileAlternative selected. The condition expression tests only that the customer is residential."})

(defn- multipliers-sentence [jurisdictions pcts]
  (->> jurisdictions
       (group-by #(pcts (first %)))
       (sort-by (fn [[_ js]]
                  (.indexOf ^java.util.List jurisdictions (first js))))
       (map (fn [[pct js]]
              (str (words/and-list (map #(nth % 2) js))
                   " "
                   (u/plain pct)
                   " percent")))
       (str/join "; ")))

(defn- per-kwh-sentence [jurisdictions charges]
  (let [names (into {}
                    (map (juxt first second))
                    jurisdictions)]
    (words/and-list
     (for [[j rows] charges]
       (str (u/plain (reduce +
                             (map last rows)))
            " cents per kWh in "
            (names j)
            " ("
            (str/join ", "
                      (for [[_ label c] rows]
                        (str label " " (u/plain c))))
            ")")))))

(defn modifier
  [{:keys [schedule versions] :as doc} date next]
  (let [pcts (versions date)
        source (as-of scl/ordinance date)
        charges (as-of scl/rss-undergrounding date)
        charges-from (effective-key scl/rss-undergrounding date)
        base-date (effective-key rts/rts-rates date)
        words (merge doc
                     {:effective (words/long-date date)
                      :next next
                      :base-identifier (:identifier rts/rts)
                      :base-name (:name rts/rts)
                      :multipliers (multipliers-sentence scl/rss-jurisdictions pcts)
                      :per-kwh-since (words/long-date (since scl/rss-undergrounding date))
                      :per-kwh (per-kwh-sentence scl/rss-jurisdictions charges)})
        {:keys [version superseded eligibility-name eligibility]} prose]
    (alt/package
     (merge doc
            {:utility scl/scl
             :version date
             :next next
             :source source
             :pages (get-in source [:pages (keyword schedule)])
             :base (:schedule rts/rts)
             :base-ids (tou/ids (first (:prefix scl/scl))
                                (:schedule rts/rts)
                                base-date
                                :base-service-charge)
             :alternatives (mapv (comp vec (partial take 2))
                                 scl/rss-jurisdictions)
             :percentages pcts
             :per-kwh charges
             :per-kwh-since charges-from
             :description (cond-> (u/fill version words)
                            next (str " " (u/fill superseded words)))
             :eligibility {:name eligibility-name
                           :description eligibility
                           :customer-kind :urpx/residentialKind}
             :coverage {:result :urpx/complete}}))))

(defurpx :rate-plans.kind/document residential-suburban
  {:kind :rate-plan-modifier
   :utility scl/scl
   :schedule "residential-suburban"
   :identifier "RSS-RTS-SUBURBAN"
   :name "Residential Suburban Franchise and Tax Multipliers and Undergrounding Charges"
   :initial-effective-date "2024-01-01"
   :dimension {:slug "jurisdiction"
               :property "serviceJurisdiction"
               :display-name "Suburban jurisdiction"
               :name "Location of service: the suburban jurisdiction the customer is served in"}
   :multipliers
   [{:slug "franchise-tax-energy"
     :metric "mi-energy"
     :based-on :summary-energy
     :ledger-name "Franchise and Tax Multiplier, Energy Charge"
     :pd-name "Suburban franchise and tax multiplier on the Schedule RTS energy charge"
     :of-what "the Schedule RTS energy charge"}
    {:slug "franchise-tax-base-service-charge"
     :metric "mi-meter-count"
     :based-on :price-fixed
     :per-day? true
     :ledger-name "Franchise and Tax Multiplier, Base Service Charge"
     :pd-name "Suburban franchise and tax multiplier on the Schedule RTS Base Service Charge, per meter per day"
     :of-what "the Schedule RTS Base Service Charge"}]
   :names {:multiplier "franchise and tax multiplier"
           :psa "Franchise and tax multiplier and undergrounding charges, by location of service"
           :per-kwh-slug "undergrounding"
           :per-kwh-suffix " Undergrounding Charge"
           :per-kwh-ledger "Suburban Undergrounding Charges"}
   :versions scl/rss-multipliers
   :expand modifier})
