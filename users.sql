CREATE TABLE users (
  id VARCHAR(50) NOT NULL UNIQUE,
  username VARCHAR(50),
  first_name VARCHAR(50),
  last_name VARCHAR(50),
  created_at timestamp default now(),
  last_login timestamp default now(),
  PRIMARY KEY (id)
);
