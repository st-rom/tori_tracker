CREATE TABLE favourites (
  id VARCHAR(50) NOT NULL UNIQUE,
  user_id VARCHAR(50) REFERENCES users (id),
  url VARCHAR(300) UNIQUE,
  title VARCHAR(150),
  price INT,
  image_url VARCHAR(300),
  item_added timestamp,
  listing_type VARCHAR(50),
  is_deleted BOOLEAN DEFAULT FALSE,
  created_at timestamp default now(),
  PRIMARY KEY (id)
);
