# AWS migration runbook

This document describes the planned move from Supabase to AWS without changing the live application until cutover day.

## Target architecture

- **Application:** continue hosting the FastAPI application on Vercel initially.
- **Region:** Mumbai, `ap-south-1`, for all AWS resources.
- **Database:** Amazon RDS for PostgreSQL, in a private network.
- **Invoice storage:** a private Amazon S3 bucket, with encrypted objects and short-lived download/upload links.
- **Sign-in:** Amazon Cognito user pool with email/password login and TOTP MFA.

Keeping the application on Vercel for the first migration limits the amount of change at once. Hosting can move to AWS later if desired.

## What migrates directly

- All transaction, recommendation, invoice-metadata, and draft records from the existing PostgreSQL database.
- All invoice files from the `travel-invoices` bucket, retaining their transaction association and filenames.
- The application’s card rules and configuration, which are already stored in the repository.

## What requires a user action

Supabase password hashes and enrolled MFA factors cannot be moved to Cognito. Each permitted employee will be created in Cognito and will receive a password-reset invitation. They will then set a password and enrol MFA once.

## Preparation checklist

1. Create the AWS resources in `ap-south-1`: RDS PostgreSQL, private S3 bucket, Cognito user pool, and least-privilege application credentials.
2. Create an RDS backup and a verified export of the current Supabase database.
3. Create a verified copy of every invoice file and compare the count with invoice metadata.
4. Update the application to use RDS, S3 presigned links, and Cognito token verification.
5. Deploy this version as a protected test environment and run the checks below.

## Verification checklist

- Transaction count matches the Supabase export.
- Invoice metadata count matches the number of copied S3 objects.
- Representative invoice downloads work for each supported file type.
- Employees can sign in, view historical transactions, add a transaction, upload multiple invoices, and download account archives.
- Existing reports and PDF generation agree with the original records.

## Cutover and rollback

1. Temporarily put the old site in read-only mode.
2. Import the final database changes and any invoices added after the first copy.
3. Point the production application configuration to AWS and deploy.
4. Perform the verification checklist in production, then release the password-reset instructions.
5. Retain Supabase unchanged and read-only for 30 days.

If a critical issue is found during cutover, restore the prior Vercel configuration and return the application to Supabase. No source data will be deleted until the 30-day verification window ends.
