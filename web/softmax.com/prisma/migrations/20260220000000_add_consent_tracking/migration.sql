-- AlterTable
ALTER TABLE "User" ADD COLUMN "tosAcceptedAt" TIMESTAMP(3),
ADD COLUMN "tosVersion" TEXT,
ADD COLUMN "consentServiceUpdates" BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN "consentMarketing" BOOLEAN NOT NULL DEFAULT false;

-- CreateTable
CREATE TABLE "ConsentRecord" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "consentType" TEXT NOT NULL,
    "granted" BOOLEAN NOT NULL,
    "version" TEXT,
    "ipAddress" TEXT,
    "userAgent" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ConsentRecord_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "ConsentRecord_consentType_check"
      CHECK ("consentType" IN ('tos', 'comms_service', 'comms_marketing'))
);

-- CreateIndex
CREATE INDEX "ConsentRecord_userId_consentType_idx" ON "ConsentRecord"("userId", "consentType");

-- AddForeignKey
ALTER TABLE "ConsentRecord" ADD CONSTRAINT "ConsentRecord_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Backfill: existing users with profileCompleted=true get legacy ToS consent.
-- IDs use 'mig_' prefix + UUID to distinguish from app-generated cuid2 IDs.
-- createdAt uses updatedAt as best approximation of when user last accepted terms.
UPDATE "User" SET "tosAcceptedAt" = "updatedAt", "tosVersion" = 'legacy'
WHERE "profileCompleted" = true;

INSERT INTO "ConsentRecord" ("id", "userId", "consentType", "granted", "version", "createdAt")
SELECT 'mig_' || gen_random_uuid()::text, "id", 'tos', true, 'legacy', "updatedAt"
FROM "User" WHERE "profileCompleted" = true;
