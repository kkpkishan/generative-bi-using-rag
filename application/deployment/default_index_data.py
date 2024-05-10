bulk_questions = [
    {"question": "What is the average price of products purchased by female users under 30?",
     "sql": '''SELECT AVG(price)
FROM interactions i
JOIN items it ON i.item_id = it.item_id
JOIN users u ON i.user_id = u.user_id
WHERE u.gender = 'female' AND u.age < 30 AND i.event_type = 'purchase'
'''},
    {"question": "What are the top 3 product categories most viewed by male users over 40?",
     "sql": '''SELECT category_l1, COUNT(*) AS views
FROM interactions i
JOIN items it ON i.item_id = it.item_id
JOIN users u ON i.user_id = u.user_id
WHERE u.gender = 'male' AND u.age > 40 AND i.event_type = 'view'
GROUP BY category_l1
ORDER BY views DESC
LIMIT 3
'''},
    {"question": "How many discount products are purchased by users aged 18-25?",
     "sql": '''SELECT COUNT(DISTINCT item_id)
FROM interactions i
JOIN users u ON i.user_id = u.user_id
WHERE u.age BETWEEN 18 AND 25
AND i.event_type = 'purchase'
AND i.discount != ''
'''},
    {"question": "What is the conversion rate from views to purchases for each product category?",
     "sql": '''WITH views AS (
  SELECT category_l1, COUNT(*) AS views
  FROM interactions i
  JOIN items it ON i.item_id = it.item_id
  WHERE i.event_type = 'view'
  GROUP BY category_l1
),
purchases AS (
  SELECT category_l1, COUNT(*) AS purchases
  FROM interactions i
  JOIN items it ON i.item_id = it.item_id
  WHERE i.event_type = 'purchase'
  GROUP BY category_l1
)
SELECT v.category_l1, purchases / views AS conversion_rate
FROM views v
JOIN purchases p ON v.category_l1 = p.category_l1
'''},
    {"question": "What are the top 5 most viewed products by users under 30?",
     "sql": '''SELECT item_id, COUNT(*) AS views
FROM interactions i
JOIN users u ON i.user_id = u.user_id
WHERE u.age < 30
AND i.event_type = 'view'
GROUP BY item_id
ORDER BY views DESC
LIMIT 5
'''},
    {"question": "In the past 30 days, how many male and female users have completed a purchase?",
     "sql": '''
SELECT gender, COUNT(DISTINCT user_id) AS users
FROM interactions i
JOIN users u ON i.user_id = u.user_id
WHERE i.event_type = 'purchase'
AND i.timestamp >= UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 30 DAY))
GROUP BY gender
'''},
    {"question": "What is the age distribution of users who purchase products priced over $50?",
     "sql": '''SELECT age, COUNT(DISTINCT i.user_id) AS users
FROM interactions i
JOIN users u ON i.user_id = u.user_id 
JOIN items it ON i.item_id = it.item_id
WHERE i.event_type = 'purchase'
AND it.price > 50
GROUP BY age
'''},
    {"question": "What is the most common category of discount products purchased by female users under 25?",
     "sql": '''SELECT category_l1, COUNT(*) AS purchases
FROM interactions i
JOIN items it ON i.item_id = it.item_id
JOIN users u ON i.user_id = u.user_id
WHERE u.gender = 'female' AND u.age < 25
AND i.discount != ''
AND i.event_type = 'purchase'
GROUP BY category_l1
ORDER BY purchases DESC
LIMIT 1
'''},
    {"question": "How many products are purchased multiple times by the same user?",
     "sql": '''SELECT COUNT(*)
FROM (
  SELECT item_id, user_id, COUNT(*) AS num_purchases
  FROM interactions
  WHERE event_type = 'purchase'
  GROUP BY item_id, user_id
  HAVING num_purchases > 1
) t
'''},
    {"question": "Which products have been viewed but never purchased?",
     "sql": '''SELECT item_id
FROM interactions i
WHERE i.event_type = 'view'
AND item_id NOT IN (
  SELECT item_id
  FROM interactions
  WHERE event_type = 'purchase'
)
'''},
    {"question": "What is the total revenue from purchases made by users aged 30 to 40?",
     "sql": '''SELECT SUM(price) AS total_revenue
FROM interactions i
JOIN items it ON i.item_id = it.item_id
JOIN users u ON i.user_id = u.user_id
WHERE u.age BETWEEN 30 AND 40
AND i.event_type = 'purchase'
'''},
    {"question": "What is the average number of times each product is added to the cart?",
     "sql": '''SELECT item_id, AVG(added_to_cart) AS avg_cart_adds
FROM (
  SELECT item_id, COUNT(*) AS added_to_cart
  FROM interactions
  WHERE event_type = 'add_to_cart'
  GROUP BY item_id
) t
GROUP BY item_id
'''},
    {"question": "What percentage of purchases made by female users are for products priced below $10?",
     "sql": '''WITH purchases AS (
  SELECT *
  FROM interactions i
  JOIN items it ON i.item_id = it.item_id
  WHERE i.event_type = 'purchase' AND price < 10
)

SELECT COUNT(*) / (SELECT COUNT(*) FROM purchases) AS percentage
FROM purchases p
JOIN users u ON p.user_id = u.user_id
WHERE u.gender = 'female'
'''},
    {"question": "What is the click-through rate from viewing products to viewing product details?",
     "sql": '''WITH product_views AS (
  SELECT COUNT(*) AS views
  FROM interactions
  WHERE event_type = 'view'
),

detail_views AS (
  SELECT COUNT(*) AS detail_views
  FROM interactions
  WHERE event_type = 'detail_view'
)

SELECT detail_views / views AS ctr
FROM product_views, detail_views
'''},
    {"question": "What are the top 3 most frequently purchased product categories by users under 25, and what is the average number of purchases for each category?",
     "sql": '''SELECT category_l1, COUNT(*) AS purchases
FROM interactions i
JOIN items it ON i.item_id = it.item_id
JOIN users u ON i.user_id = u.user_id
WHERE u.age < 25 AND i.event_type = 'purchase'
GROUP BY category_l1
ORDER BY purchases DESC
LIMIT 3
'''},
    {"question": "What is the average number of purchases per product?",
     "sql": '''SELECT item_id, AVG(purchases) AS avg_purchases
FROM (
  SELECT item_id, COUNT(*) AS purchases
  FROM interactions
  WHERE event_type = 'purchase'
  GROUP BY item_id
) t
GROUP BY item_id
'''},
    {"question": "What percentage of purchases by male users involve a discount of more than 30%?",
     "sql": '''WITH male_purchases AS (
  SELECT *
  FROM interactions i
  JOIN users u ON i.user_id = u.user_id
  WHERE u.gender = 'male' AND i.event_type = 'purchase'
)

SELECT COUNT(*) / (SELECT COUNT(*) FROM male_purchases) AS percentage
FROM male_purchases
WHERE CAST(discount AS FLOAT) > 0.3
'''},
    {"question": "How many users have only browsed but never purchased any product?",
     "sql": '''SELECT COUNT(DISTINCT user_id)
FROM interactions
WHERE user_id NOT IN (
  SELECT DISTINCT user_id
  FROM interactions
  WHERE event_type = 'purchase'
)
AND event_type = 'view'
'''},
    {"question": "Which categories have the highest and lowest conversion rates from view to purchase?",
     "sql": '''WITH views AS (
  SELECT category_l1, COUNT(*) AS views
  FROM interactions i
  JOIN items it ON i.item_id = it.item_id
  WHERE event_type = 'view'
  GROUP BY category_l1
),

purchases AS (
  SELECT category_l1, COUNT(*) AS purchases
  FROM interactions i
  JOIN items it ON i.item_id = it.item_id
  WHERE event_type = 'purchase'
  GROUP BY category_l1
)

SELECT v.category_l1, purchases/views AS conversion_rate
FROM views v
JOIN purchases p ON v.category_l1 = p.category_l1
ORDER BY conversion_rate DESC
LIMIT 1

UNION

SELECT v.category_l1, purchases/views AS conversion_rate
FROM views v
JOIN purchases p ON v.category_l1 = p.category_l1
ORDER BY conversion_rate ASC
LIMIT 1
'''},
    {"question": "Which product has the highest conversion rate from views to purchases?",
     "sql": '''WITH views AS (
  SELECT item_id, COUNT(*) AS views
  FROM interactions
  WHERE event_type = 'view'
  GROUP BY item_id
),

purchases AS (
  SELECT item_id, COUNT(*) AS purchases
  FROM interactions
  WHERE event_type = 'purchase'
  GROUP BY item_id
)

SELECT v.item_id, purchases/views AS view_to_purchase_pct
FROM views v
JOIN purchases p ON v.item_id = p.item_id
ORDER BY view_to_purchase_pct DESC
LIMIT 1
'''},
]

for q in bulk_questions:
    q['profile'] = 'shopping_guide'
