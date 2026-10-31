-- CalorAI MySQL schema (generated from app/models.py). The backend creates these tables
-- automatically on first start; this file is for documentation / manual setup.
CREATE DATABASE IF NOT EXISTS calorai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE calorai;

CREATE TABLE food_item (
	food_id INTEGER NOT NULL AUTO_INCREMENT, 
	food_name VARCHAR(100) NOT NULL, 
	food_category VARCHAR(50) NOT NULL, 
	calories_per_100g NUMERIC(6, 2) NOT NULL, 
	carbs_per_100g NUMERIC(6, 2) NOT NULL, 
	protein_per_100g NUMERIC(6, 2) NOT NULL, 
	fat_per_100g NUMERIC(6, 2) NOT NULL, 
	sugar_per_100g NUMERIC(6, 2) NOT NULL, 
	sodium_per_100g NUMERIC(6, 2) NOT NULL, 
	fibre_per_100g NUMERIC(6, 2) NOT NULL, 
	allergen_tags VARCHAR(100), 
	PRIMARY KEY (food_id)
) ENGINE=InnoDB;
CREATE INDEX ix_food_item_food_name ON food_item (food_name);

CREATE TABLE user (
	user_id INTEGER NOT NULL AUTO_INCREMENT, 
	full_name VARCHAR(100) NOT NULL, 
	email VARCHAR(100) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	age INTEGER NOT NULL, 
	gender VARCHAR(20) NOT NULL, 
	height_cm NUMERIC(5, 2) NOT NULL, 
	weight_kg NUMERIC(5, 2) NOT NULL, 
	activity_level VARCHAR(30) NOT NULL, 
	health_goal VARCHAR(50) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (user_id)
) ENGINE=InnoDB;
CREATE UNIQUE INDEX ix_user_email ON user (email);

CREATE TABLE daily_summary (
	summary_id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	summary_date DATE NOT NULL, 
	total_calories NUMERIC(6, 2) NOT NULL, 
	total_carbs NUMERIC(6, 2) NOT NULL, 
	total_protein NUMERIC(6, 2) NOT NULL, 
	total_fat NUMERIC(6, 2) NOT NULL, 
	total_sugar NUMERIC(6, 2) NOT NULL, 
	total_sodium NUMERIC(6, 2) NOT NULL, 
	calorie_goal NUMERIC(6, 2) NOT NULL, 
	generated_at DATETIME NOT NULL, 
	PRIMARY KEY (summary_id), 
	CONSTRAINT uq_user_date UNIQUE (user_id, summary_date), 
	FOREIGN KEY(user_id) REFERENCES user (user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE dietary_profile (
	profile_id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	religious_restriction VARCHAR(50), 
	diet_preference VARCHAR(20) NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (profile_id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES user (user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE meal (
	meal_id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	meal_category VARCHAR(20) NOT NULL, 
	meal_datetime DATETIME NOT NULL, 
	source_type VARCHAR(20) NOT NULL, 
	total_calories NUMERIC(6, 2) NOT NULL, 
	total_carbs NUMERIC(6, 2) NOT NULL, 
	total_protein NUMERIC(6, 2) NOT NULL, 
	total_fat NUMERIC(6, 2) NOT NULL, 
	total_sugar NUMERIC(6, 2) NOT NULL, 
	total_sodium NUMERIC(6, 2) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (meal_id), 
	FOREIGN KEY(user_id) REFERENCES user (user_id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE INDEX ix_meal_meal_datetime ON meal (meal_datetime);
CREATE INDEX ix_meal_user_id ON meal (user_id);

CREATE TABLE allergy (
	allergy_id INTEGER NOT NULL AUTO_INCREMENT, 
	profile_id INTEGER NOT NULL, 
	allergen_name VARCHAR(50) NOT NULL, 
	PRIMARY KEY (allergy_id), 
	FOREIGN KEY(profile_id) REFERENCES dietary_profile (profile_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE meal_item (
	meal_item_id INTEGER NOT NULL AUTO_INCREMENT, 
	meal_id INTEGER NOT NULL, 
	food_id INTEGER NOT NULL, 
	portion_size_g NUMERIC(6, 2) NOT NULL, 
	calories NUMERIC(6, 2) NOT NULL, 
	carbs NUMERIC(6, 2) NOT NULL, 
	protein NUMERIC(6, 2) NOT NULL, 
	fat NUMERIC(6, 2) NOT NULL, 
	sugar NUMERIC(6, 2) NOT NULL, 
	sodium NUMERIC(6, 2) NOT NULL, 
	PRIMARY KEY (meal_item_id), 
	FOREIGN KEY(meal_id) REFERENCES meal (meal_id) ON DELETE CASCADE, 
	FOREIGN KEY(food_id) REFERENCES food_item (food_id)
) ENGINE=InnoDB;
CREATE INDEX ix_meal_item_meal_id ON meal_item (meal_id);

CREATE TABLE meal_score (
	score_id INTEGER NOT NULL AUTO_INCREMENT, 
	meal_id INTEGER NOT NULL, 
	overall_score NUMERIC(5, 2) NOT NULL, 
	feedback_text TEXT NOT NULL, 
	PRIMARY KEY (score_id), 
	UNIQUE (meal_id), 
	FOREIGN KEY(meal_id) REFERENCES meal (meal_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE medical_condition (
	condition_id INTEGER NOT NULL AUTO_INCREMENT, 
	profile_id INTEGER NOT NULL, 
	condition_name VARCHAR(50) NOT NULL, 
	PRIMARY KEY (condition_id), 
	FOREIGN KEY(profile_id) REFERENCES dietary_profile (profile_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE notification (
	notification_id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	related_meal_id INTEGER, 
	notification_type VARCHAR(30) NOT NULL, 
	message VARCHAR(255) NOT NULL, 
	is_read BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (notification_id), 
	FOREIGN KEY(user_id) REFERENCES user (user_id) ON DELETE CASCADE, 
	FOREIGN KEY(related_meal_id) REFERENCES meal (meal_id) ON DELETE SET NULL
) ENGINE=InnoDB;
CREATE INDEX ix_notification_created_at ON notification (created_at);
CREATE INDEX ix_notification_user_id ON notification (user_id);

CREATE TABLE nutrition_risk (
	risk_id INTEGER NOT NULL AUTO_INCREMENT, 
	score_id INTEGER NOT NULL, 
	risk_type VARCHAR(30) NOT NULL, 
	severity VARCHAR(10) NOT NULL, 
	PRIMARY KEY (risk_id), 
	FOREIGN KEY(score_id) REFERENCES meal_score (score_id) ON DELETE CASCADE
) ENGINE=InnoDB;
