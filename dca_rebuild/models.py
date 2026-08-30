from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


# ============================================================
# DCA EDITIONS
# One record per Dancer's Choice Awards cycle/year.
# ============================================================

class DCAEdition(Base):
    __tablename__ = "ledger_dca_editions"

    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False, unique=True)

    title = Column(String(200), nullable=False)

    # draft
    # category_suggestions
    # category_voting
    # nominations
    # nominee_voting
    # results
    # archived
    phase = Column(String(50), nullable=False, default="draft")

    is_public = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    categories = relationship(
        "DCACategory",
        back_populates="edition",
        cascade="all, delete-orphan",
    )


# ============================================================
# CATEGORIES
#
# Stores both historical and current categories.
#
# 2023 categories can be attached to the 2023 edition.
# A later edition can reference the historical category it
# originated from.
# ============================================================

class DCACategory(Base):
    __tablename__ = "ledger_dca_categories"

    id = Column(Integer, primary_key=True)

    edition_id = Column(
        Integer,
        ForeignKey("ledger_dca_editions.id"),
        nullable=False,
    )

    name = Column(String(250), nullable=False)
    normalized_name = Column(String(250), nullable=False)

    description = Column(Text)

    # historical
    # returning
    # new
    source_type = Column(String(50), nullable=False)

    # If this category came from an older DCA category,
    # this points back to it.
    source_category_id = Column(
        Integer,
        ForeignKey("ledger_dca_categories.id"),
        nullable=True,
    )

    # candidate / approved / rejected / official
    status = Column(String(50), nullable=False, default="candidate")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    edition = relationship(
        "DCAEdition",
        back_populates="categories",
        foreign_keys=[edition_id],
    )

    source_category = relationship(
        "DCACategory",
        remote_side=[id],
        foreign_keys=[source_category_id],
    )

    __table_args__ = (
        UniqueConstraint(
            "edition_id",
            "normalized_name",
            name="ledger_uq_dca_category_edition_name",
        ),
    )


# ============================================================
# ROUND 1 — CATEGORY SUGGESTION SUBMISSION
#
# One person can submit again after 24 hours.
# Each submission groups:
#   - Yes/No votes on 2023 categories
#   - new category suggestions
#   - category-count preference
# ============================================================

class DCACategorySuggestionSubmission(Base):
    __tablename__ = "ledger_dca_category_suggestion_submissions"

    id = Column(Integer, primary_key=True)

    edition_id = Column(
        Integer,
        ForeignKey("ledger_dca_editions.id"),
        nullable=False,
    )

    # Never displayed publicly.
    email_hash = Column(String(128), nullable=False)

    # Additional anti-abuse identifiers.
    ip_hash = Column(String(128))
    visitor_key = Column(String(128))

    submitted_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # top_25
    # top_25 | threshold | all
    # threshold
    # all
    category_count_preference = Column(String(50), nullable=False)

    return_votes = relationship(
        "DCAReturnCategoryVote",
        back_populates="submission",
        cascade="all, delete-orphan",
    )

    suggestions = relationship(
        "DCANewCategorySuggestion",
        back_populates="submission",
        cascade="all, delete-orphan",
    )


# ============================================================
# ROUND 1 — YES / NO ON RETURNING 2023 CATEGORIES
# ============================================================

class DCAReturnCategoryVote(Base):
    __tablename__ = "ledger_dca_return_category_votes"

    id = Column(Integer, primary_key=True)

    submission_id = Column(
        Integer,
        ForeignKey("ledger_dca_category_suggestion_submissions.id"),
        nullable=False,
    )

    category_id = Column(
        Integer,
        ForeignKey("ledger_dca_categories.id"),
        nullable=False,
    )

    bring_back = Column(Boolean, nullable=False)

    submission = relationship(
        "DCACategorySuggestionSubmission",
        back_populates="return_votes",
    )

    __table_args__ = (
        UniqueConstraint(
            "submission_id",
            "category_id",
            name="ledger_uq_dca_return_vote_submission_category",
        ),
    )


# ============================================================
# ROUND 1 — NEW CATEGORY SUGGESTIONS
# ============================================================

class DCANewCategorySuggestion(Base):
    __tablename__ = "ledger_dca_new_category_suggestions"

    id = Column(Integer, primary_key=True)

    submission_id = Column(
        Integer,
        ForeignKey("ledger_dca_category_suggestion_submissions.id"),
        nullable=False,
    )

    category_name = Column(String(250), nullable=False)
    normalized_name = Column(String(250), nullable=False)

    # pending / approved / merged / rejected
    moderation_status = Column(
        String(50),
        nullable=False,
        default="pending",
    )

    # Used when several differently-worded suggestions
    # are determined to represent the same category.
    merged_into_id = Column(
        Integer,
        ForeignKey("ledger_dca_new_category_suggestions.id"),
        nullable=True,
    )

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    submission = relationship(
        "DCACategorySuggestionSubmission",
        back_populates="suggestions",
    )

    merged_into = relationship(
        "DCANewCategorySuggestion",
        remote_side=[id],
        foreign_keys=[merged_into_id],
    )


# ============================================================
# ROUND 2 — CATEGORY BALLOT
#
# Created only after Round 1 closes and admin approves
# the candidate category list.
# ============================================================

class DCACategoryBallot(Base):
    __tablename__ = "ledger_dca_category_ballots"

    id = Column(Integer, primary_key=True)

    edition_id = Column(
        Integer,
        ForeignKey("ledger_dca_editions.id"),
        nullable=False,
    )

    opened_at = Column(DateTime)
    closed_at = Column(DateTime)

    # The option that won the Round 1 preliminary survey.
    round_one_winning_method = Column(String(50))

    # Participation-derived threshold shown during Round 2.
    threshold_number = Column(Integer)

    # The binding method selected by Round 2.
    final_method = Column(String(50))

    is_open = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ============================================================
# ROUND 2 — PARTICIPANT SUBMISSION
# ============================================================

class DCACategoryBallotSubmission(Base):
    __tablename__ = "ledger_dca_category_ballot_submissions"

    id = Column(Integer, primary_key=True)

    ballot_id = Column(
        Integer,
        ForeignKey("ledger_dca_category_ballots.id"),
        nullable=False,
    )

    email_hash = Column(String(128), nullable=False)
    ip_hash = Column(String(128))
    visitor_key = Column(String(128))

    submitted_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # The final category-count/method vote.
    #
    # This can be:
    #   the Round 1 winning fixed option,
    #   threshold,
    #   all
    final_method_vote = Column(String(50), nullable=False)


# ============================================================
# ROUND 2 — CATEGORY VOTES
#
# A submission can vote for multiple categories.
# ============================================================

class DCACategoryBallotVote(Base):
    __tablename__ = "ledger_dca_category_ballot_votes"

    id = Column(Integer, primary_key=True)

    submission_id = Column(
        Integer,
        ForeignKey("ledger_dca_category_ballot_submissions.id"),
        nullable=False,
    )

    category_id = Column(
        Integer,
        ForeignKey("ledger_dca_categories.id"),
        nullable=False,
    )

    selected = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint(
            "submission_id",
            "category_id",
            name="ledger_uq_dca_ballot_vote_submission_category",
        ),
    )


# ============================================================
# PERMANENT ROUND RESULTS / METHODOLOGY
#
# This lets the archive explain HOW an edition was decided,
# rather than only showing the eventual winners.
# ============================================================

class DCARoundRecord(Base):
    __tablename__ = "ledger_dca_round_records"

    id = Column(Integer, primary_key=True)

    edition_id = Column(
        Integer,
        ForeignKey("ledger_dca_editions.id"),
        nullable=False,
    )

    round_name = Column(String(100), nullable=False)

    opened_at = Column(DateTime)
    closed_at = Column(DateTime)

    participant_count = Column(Integer, nullable=False, default=0)
    submission_count = Column(Integer, nullable=False, default=0)

    methodology = Column(Text)
    results_snapshot = Column(Text)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class LFAArchiveSubmission(Base):
    __tablename__ = "ledger_lfa_archive_submissions"

    id = Column(Integer, primary_key=True)

    year = Column(Integer, nullable=False)

    submission_type = Column(
        String(30),
        nullable=False,
        default="missing_information"
    )

    category_name = Column(String(255), nullable=False)
    winner_name = Column(String(255), nullable=False)

    team_name = Column(String(255), nullable=True)
    additional_details = Column(Text, nullable=True)
    source_information = Column(Text, nullable=True)

    submitter_email = Column(String(255), nullable=True)

    status = Column(
        String(30),
        nullable=False,
        default="pending"
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )



# ============================================================
# LITEFEET AWARDS — VERIFIED ARCHIVE RECORDS
# ============================================================

class LFARecord(Base):
    __tablename__ = "ledger_lfa_records"

    id = Column(Integer, primary_key=True)

    year = Column(Integer, nullable=False)

    record_type = Column(
        String(30),
        nullable=False
    )

    category_name = Column(
        String(255),
        nullable=False
    )

    person_name = Column(
        String(255),
        nullable=False
    )

    team_name = Column(
        String(255),
        nullable=True
    )

    additional_details = Column(
        Text,
        nullable=True
    )

    source_information = Column(
        Text,
        nullable=True
    )

    source_submission_id = Column(
        Integer,
        nullable=True,
        index=True
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )


# ============================================================
# LITEFEET LEDGER — BETA FEATURE FLAGS
# ============================================================

class BetaFeatureFlag(Base):
    __tablename__ = "ledger_beta_feature_flags"

    id = Column(Integer, primary_key=True)

    feature_key = Column(
        String(100),
        nullable=False,
        unique=True,
        index=True
    )

    name = Column(
        String(150),
        nullable=False
    )

    description = Column(
        Text,
        nullable=True
    )

    visibility = Column(
        String(20),
        nullable=False,
        default="private"
    )

    sort_order = Column(
        Integer,
        nullable=False,
        default=0
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


# ============================================================
# LITEFEET LEDGER — BETA FEEDBACK
# ============================================================

class BetaFeedback(Base):
    __tablename__ = "ledger_beta_feedback"

    id = Column(Integer, primary_key=True)

    email = Column(
        String(255),
        nullable=False,
        index=True
    )

    feature_key = Column(
        String(100),
        nullable=True,
        index=True
    )

    feedback_type = Column(
        String(30),
        nullable=False,
        default="general"
    )

    message = Column(
        Text,
        nullable=False
    )

    page_path = Column(
        String(500),
        nullable=True
    )

    status = Column(
        String(30),
        nullable=False,
        default="new",
        index=True
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )


# ============================================================
# LITEFEET LEDGER — BETA CHANGELOG
# ============================================================

class BetaChangelog(Base):
    __tablename__ = "ledger_beta_changelog"

    id = Column(Integer, primary_key=True)

    title = Column(
        String(255),
        nullable=False
    )

    details = Column(
        Text,
        nullable=False
    )

    visibility = Column(
        String(20),
        nullable=False,
        default="beta"
    )

    is_published = Column(
        Boolean,
        nullable=False,
        default=True
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )


# ============================================================
# LITEFEET LEDGER — NEWSLETTER SUBSCRIBERS
# ============================================================

class NewsletterSubscriber(Base):
    __tablename__ = "ledger_newsletter_subscribers"

    id = Column(Integer, primary_key=True)

    email = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True
    )

    subscribed_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    unsubscribed_at = Column(
        DateTime,
        nullable=True
    )

# ============================================================
# LITEFEET LEDGER — ARCHIVE FOUNDATION
# ============================================================

class LedgerEra(Base):
    __tablename__ = "ledger_eras"

    id = Column(
        Integer,
        primary_key=True,
    )

    name = Column(
        String(150),
        nullable=False,
        unique=True,
        index=True,
    )

    slug = Column(
        String(160),
        nullable=False,
        unique=True,
        index=True,
    )

    description = Column(
        Text,
        nullable=True,
    )

    start_year = Column(
        Integer,
        nullable=True,
        index=True,
    )

    end_year = Column(
        Integer,
        nullable=True,
        index=True,
    )

    sort_order = Column(
        Integer,
        nullable=False,
        default=0,
        index=True,
    )

    status = Column(
        String(30),
        nullable=False,
        default="draft",
        index=True,
    )

    source_notes = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
