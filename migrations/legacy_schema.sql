-- Frozen SQLite schema at cad3003. No data and no dependency on current ORM.

CREATE TABLE conflicts (
	id VARCHAR NOT NULL,
	hotel_id VARCHAR NOT NULL,
	subject_id VARCHAR NOT NULL,
	feature_key VARCHAR NOT NULL,
	left_id VARCHAR NOT NULL,
	right_id VARCHAR NOT NULL,
	created_at VARCHAR NOT NULL,
	policy VARCHAR NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(hotel_id) REFERENCES hotels (id),
	FOREIGN KEY(left_id) REFERENCES observations (id),
	FOREIGN KEY(right_id) REFERENCES observations (id)
);

CREATE TABLE environment_reports (
	id VARCHAR NOT NULL,
	hotel_id VARCHAR NOT NULL,
	kind VARCHAR NOT NULL,
	collected_at VARCHAR NOT NULL,
	payload JSON NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(hotel_id) REFERENCES hotels (id)
);

CREATE TABLE evidence (
	observation_id VARCHAR NOT NULL,
	source_id VARCHAR NOT NULL,
	payload JSON NOT NULL,
	PRIMARY KEY (observation_id),
	FOREIGN KEY(observation_id) REFERENCES observations (id),
	FOREIGN KEY(source_id) REFERENCES sources (id)
);

CREATE TABLE feature_definitions (
	"key" VARCHAR NOT NULL,
	payload JSON NOT NULL,
	PRIMARY KEY ("key")
);

CREATE TABLE hotelier_answers (
	id VARCHAR NOT NULL,
	question_id VARCHAR NOT NULL,
	text VARCHAR NOT NULL,
	extraction JSON NOT NULL,
	status VARCHAR NOT NULL,
	simulated BOOLEAN NOT NULL,
	created_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(question_id) REFERENCES hotelier_questions (id)
);

CREATE TABLE hotelier_questions (
	id VARCHAR NOT NULL,
	hotel_id VARCHAR NOT NULL,
	feature_key VARCHAR NOT NULL,
	text VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	created_at VARCHAR NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (hotel_id, feature_key),
	FOREIGN KEY(hotel_id) REFERENCES hotels (id)
);

CREATE TABLE hotels (
	id VARCHAR NOT NULL,
	payload JSON NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE observations (
	id VARCHAR NOT NULL,
	hotel_id VARCHAR NOT NULL,
	subject_id VARCHAR NOT NULL,
	feature_key VARCHAR NOT NULL,
	payload JSON NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(hotel_id) REFERENCES hotels (id)
);

CREATE TABLE rooms (
	id VARCHAR NOT NULL,
	hotel_id VARCHAR NOT NULL,
	number VARCHAR NOT NULL,
	floor INTEGER,
	PRIMARY KEY (id),
	FOREIGN KEY(hotel_id) REFERENCES hotels (id)
);

CREATE TABLE sources (
	id VARCHAR NOT NULL,
	payload JSON NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_conflicts_hotel_id ON conflicts (hotel_id);

CREATE INDEX ix_environment_reports_collected_at ON environment_reports (collected_at);

CREATE INDEX ix_environment_reports_hotel_id ON environment_reports (hotel_id);

CREATE INDEX ix_environment_reports_kind ON environment_reports (kind);

CREATE INDEX ix_hotelier_questions_hotel_id ON hotelier_questions (hotel_id);

CREATE INDEX ix_observations_feature_key ON observations (feature_key);

CREATE INDEX ix_observations_hotel_id ON observations (hotel_id);

CREATE INDEX ix_observations_subject_id ON observations (subject_id);

CREATE INDEX ix_rooms_hotel_id ON rooms (hotel_id);
