"""Contextual bandit: context features, Thompson Sampling, and reward posting.

Split three ways on purpose. ``context`` turns a case into features and a bucket
string and knows nothing about probability; ``thompson`` samples and updates Beta
posteriors and knows nothing about cases; ``reward`` closes the loop between
them. The decide step composes all three, and each piece is testable without a
database or a case.
"""
