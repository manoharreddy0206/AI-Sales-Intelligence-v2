# Metrics glossary

Definitions used by the dashboard and the Sales Analyst Copilot. Each entry has a
stable ID in braces; the copilot cites these IDs. Every definition points to the
code that implements it. Change the code and this file together.

## Revenue {#revenue}
Aliases: sales, total sales, turnover, gross revenue
Source: backend/app/analytics.py `summary`
Revenue is the sum of the `amount` column for all stored orders whose `order_date` falls inside the selected range, rounded to two decimal places. Start and end dates are inclusive. Amounts are taken as uploaded: there is no tax, refund, discount or currency adjustment.

## Order count {#orders}
Aliases: orders, number of orders, transactions
Source: backend/app/analytics.py `summary`; backend/app/storage.py
The number of stored orders in the selected range. `order_id` is the primary key, so an order uploaded twice is counted once. Re-uploading an order ID updates that order instead of adding a new one.

## Customers {#customers}
Aliases: customer count, unique customers, buyers
Source: backend/app/analytics.py `summary`
The number of distinct `customer_id` values among orders in the selected range.

## Average order value {#average-order-value}
Aliases: AOV, average order, mean order value, basket size
Source: backend/app/analytics.py `summary`
Revenue divided by order count for the selected range, rounded to two decimal places. When the range has no orders, the dashboard shows 0 and the copilot reports the value as not defined.

## Repeat purchase and repeat customer {#repeat-purchase}
Aliases: repeat customer, repeat buyer, returning customer, repeat purchase, repeat purchaser, retention target
Source: backend/app/comparison.py `compare`; backend/app/model.py
The app has no separate "repeat customer" count on the dashboard. "Repeat" is defined by the model target: at each month-end cutoff, a customer who already has at least one order on or before the cutoff is a repeat buyer (label 1) if they place another order in the following calendar month, and otherwise label 0. Features use only orders on or before the cutoff.

## Customer segments {#segments}
Aliases: segment, RFM, at risk, loyal, active, customer segmentation
Source: backend/app/analytics.py `segments`
Segments are rule-based, not clustering. "At risk" means recency is over 60 days. "Loyal" means the customer isn't at risk and has at least four orders. "Active" covers everyone else. Segments always use all stored orders and ignore the revenue date filter.

## Recency, frequency and monetary value {#rfm}
Aliases: recency, frequency, monetary, RFM features
Source: backend/app/analytics.py `segments`; backend/app/comparison.py
Recency is the number of days from a customer's latest order to the as-of date. Frequency is the customer's total order count. Monetary value is the customer's total spend. In segmentation, the as-of date is the latest order date in the dataset. In the model, it is each month-end cutoff.

## Relative periods such as last month {#relative-periods}
Aliases: last month, this month, latest month, previous month, as-of date, period
Source: backend/app/copilot/periods.py
The copilot anchors relative periods to the dataset's as-of date, which is the latest stored order date, not to today's date. "Last month" is the calendar month before the as-of month. "Latest month" is the as-of month and is flagged partial when the as-of date falls before that month's last day. Months run from the first to the last calendar day, inclusive.

## Period comparison and deltas {#period-comparison}
Aliases: change, delta, versus previous month, month over month, growth, percent change
Source: backend/app/copilot/tools.py `compare_periods`
A comparison reports revenue, order count and average order value for both periods. The absolute change is current minus previous. The percent change is the absolute change divided by the previous value, times 100. When the previous value is zero or not defined, the percent change is reported as not defined instead of infinite.

## Currency and amounts {#currency}
Aliases: currency, money, amount, rupees, dollars, units
Source: backend/app/ingest.py `parse_csv`; README "Input data"
All amounts are assumed to share one currency, and that currency is not stored. Amounts must be plain numbers greater than 0 and less than 1,000,000,000. Currency symbols and thousands separators are rejected. The app performs no currency conversion and shows no currency symbol.

## Upload validation {#upload-validation}
Aliases: import rules, CSV format, invalid rows, duplicate order id, upload
Source: backend/app/ingest.py
The required columns are `order_id`, `customer_id`, `order_date` (YYYY-MM-DD) and `amount`. A file that contains any invalid row is rejected as a whole, and stored orders are left unchanged. Duplicate order IDs within one file are rejected. Files are limited to 2 MB. Text dates in Excel files must also use YYYY-MM-DD. Real Excel date cells are accepted.

## Model comparison {#model-comparison}
Aliases: classifier, F1, baseline, model selection, logistic regression, random forest
Source: backend/app/comparison.py
The candidates are a majority-class baseline, logistic regression and random forest. Each candidate is trained on earlier cutoffs. The validation cutoff picks the candidate with the best F1 for the repeat-buyer class. The picked candidate is refit and scored on a later test cutoff alongside a refit baseline. The newest month is excluded because it may be incomplete.
