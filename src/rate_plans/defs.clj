;; SPDX-FileCopyrightText: 2026 Clark Communications Corporation
;; SPDX-License-Identifier: MIT
(ns rate-plans.defs
  "The corpus's kinds for urpx.defs/defurpx, qualified :rate-plans.kind/*,
   and the date-keyed lookups."
  (:require [urpx.defs :as defs]))

;; ---------------------------------------------------------------------------
;; Shared value schemas
;; ---------------------------------------------------------------------------

(def Date
  [:re
   {:error/message "should be a yyyy-mm-dd string"}
   #"^\d{4}-\d{2}-\d{2}$"])

(defn- dated
  "A map keyed by the date each value takes effect."
  [v]
  [:map-of Date v])

(def Cents
  "A rate as the tariff prints it: a BigDecimal with exactly 2 places."
  [:fn
   {:error/message "should be a BigDecimal with 2 decimal places, e.g. 16.10M"}
   #(and (decimal? %)
         (= 2 (.scale ^BigDecimal %)))])

(def Decimal
  "A figure as the tariff prints it: a BigDecimal, whose scale is the number
   of places printed, e.g. 0.05354M."
  [:fn
   {:error/message "should be a BigDecimal, e.g. 0.05354M"}
   decimal?])

(def HHMM
  [:re
   {:error/message "should be an hh:mm string from 00:00 to 24:00"}
   #"^(([01]\d|2[0-3]):[0-5]\d|24:00)$"])

(def DaySet [:enum :all :mon-sat :mon-fri :sat-sun :sat :sun])

;; ---------------------------------------------------------------------------
;; Kinds
;; ---------------------------------------------------------------------------

(defmethod defs/kind-schema :rate-plans.kind/utility [_]
  [:map
   [:key :string]
   [:prefix [:tuple :string :string]]
   [:legal-name :string]
   [:eia-id :string]
   [:timezone :string]
   [:path [:vector :string]]
   [:context {:optional true} [:map-of :string :any]]])

(defmethod defs/kind-schema :rate-plans.kind/holidays [_]
  (dated [:map
          [:named
           [:vector
            [:tuple :keyword :string :string
             [:maybe
              [:tuple
               [:int {:min 1 :max 12}]
               [:int {:min 1 :max 31}]]]]]]
          [:observed-monday-after-sunday
           [:map
            [:of [:vector :keyword]]
            [:through :int]]]]))

(defmethod defs/kind-schema :rate-plans.kind/tou-periods [_]
  (dated [:vector [:tuple :keyword :string]]))

(defmethod defs/kind-schema :rate-plans.kind/tou-brackets [_]
  (dated [:vector
          [:tuple :keyword :string DaySet HHMM HHMM
           [:maybe [:enum :excluded :only]]]]))

(defmethod defs/kind-schema :rate-plans.kind/rates [_]
  (dated [:map-of :keyword Cents]))

(defmethod defs/kind-schema :rate-plans.kind/percentages [_]
  (dated [:map-of :keyword Cents]))

(defmethod defs/kind-schema :rate-plans.kind/undergrounding [_]
  (dated [:map-of :keyword
          [:vector [:tuple :keyword :string Cents]]]))

(defmethod defs/kind-schema :rate-plans.kind/jurisdictions [_]
  [:vector [:tuple :keyword :string :string]])

(defmethod defs/kind-schema :rate-plans.kind/dollars [_]
  (dated [:map-of [:or :keyword :int] Decimal]))

(defmethod defs/kind-schema :rate-plans.kind/seasons [_]
  (dated [:vector
          [:tuple :keyword :string [:vector [:int {:min 1 :max 12}]]]]))

(defmethod defs/kind-schema :rate-plans.kind/tou-tiers [_]
  (dated [:vector
          [:tuple :keyword :string :keyword
           [:vector [:tuple [:maybe :string] HHMM HHMM]]]]))

(defmethod defs/kind-schema :rate-plans.kind/baseline-quantities [_]
  (dated [:vector
          [:tuple :string Decimal Decimal Decimal Decimal]]))

(defmethod defs/kind-schema :rate-plans.kind/income-tiers [_]
  [:vector [:tuple :keyword :string [:vector :keyword] [:vector :keyword]]])

(defmethod defs/kind-schema :rate-plans.kind/ledgers [_]
  [:vector [:tuple :keyword :string :keyword :keyword]])

(defmethod defs/kind-schema :rate-plans.kind/charges [_]
  [:vector
   [:tuple :keyword :string :keyword :keyword :keyword :keyword :keyword
    [:maybe :keyword]]])

(defmethod defs/kind-schema :rate-plans.kind/climate-credit [_]
  (dated [:map {:closed true}
          [:amount {:optional true} Decimal]
          [:months {:optional true} [:vector [:int {:min 1 :max 12}]]]]))

(defmethod defs/kind-schema :rate-plans.kind/discountable [_]
  (dated [:map-of :keyword
          [:map {:closed true}
           [:excludes [:vector :keyword]]
           [:name :string]]]))

(defmethod defs/kind-schema :rate-plans.kind/coverage [_]
  (dated [:map {:closed true}
          [:text {:optional true} :string]
          [:deferrals {:optional true} [:vector :string]]]))

(defmethod defs/kind-schema :rate-plans.kind/programs [_]
  [:vector [:tuple :keyword :string [:maybe :keyword]]])

(defmethod defs/kind-schema :rate-plans.kind/advice-letters [_]
  [:map-of :string
   [:map
    [:effective Date]
    [:received Date]
    [:description {:optional true} :string]]])

(defmethod defs/kind-schema :rate-plans.kind/decisions [_]
  [:map-of :string
   [:map
    [:url :string]
    [:description {:optional true} :string]]])

(defmethod defs/kind-schema :rate-plans.kind/filings [_]
  (dated [:map
          [:retrieved Date]
          [:leaves [:tuple :string :string]]
          [:advice-letter :string]
          [:decision {:optional true} :string]
          [:change-reason :keyword]
          [:evaluated-on Date]]))

(defmethod defs/kind-schema :rate-plans.kind/source [_]
  (dated [:map
          [:file :string]
          [:url :string]
          [:retrieved Date]
          [:evaluated-on Date]
          [:pages [:map-of :keyword [:tuple :int :int]]]]))

(defmethod defs/kind-schema :rate-plans.kind/description [_]
  [:or
   :string
   [:map-of :keyword [:or :string (dated :string)]]])

(defmethod defs/kind-schema :rate-plans.kind/document [_]
  [:map
   [:kind [:enum :rate-plan :rate-plan-modifier]]
   [:utility (defs/kind-schema :rate-plans.kind/utility)]
   [:schedule :string]
   [:identifier :string]
   [:name :string]
   [:initial-effective-date Date]
   [:filing {:optional true} :string]
   [:where {:optional true} :string]
   [:customer-choice {:optional true} :keyword]
   [:default? {:optional true} :boolean]
   [:price-summary {:optional true} :string]
   [:dimension {:optional true}
    [:map
     [:slug :string]
     [:property :string]
     [:display-name :string]
     [:name :string]]]
   [:multipliers {:optional true}
    [:vector
     [:map
      [:slug :string]
      [:metric :string]
      [:based-on :keyword]
      [:per-day? {:optional true} :boolean]
      [:ledger-name :string]
      [:pd-name :string]
      [:of-what :string]]]]
   [:names {:optional true}
    [:map
     [:multiplier :string]
     [:psa :string]
     [:per-kwh-slug :string]
     [:per-kwh-suffix :string]
     [:per-kwh-ledger :string]]]
   [:expand ifn?]
   [:versions [:map-of Date :any]]])

(defn as-of
  "The value in date-keyed map `m` in effect on `date`."
  [m date]
  (some (fn [[k v]]
          (when (<= (compare k date) 0)
            v))
        (sort-by key #(compare %2 %1) m)))
