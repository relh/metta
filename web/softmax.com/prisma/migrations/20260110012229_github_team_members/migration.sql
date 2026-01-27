-- CreateTable
CREATE TABLE "GitHubTeamMember" (
    "userId" TEXT NOT NULL,
    "login" TEXT NOT NULL,

    CONSTRAINT "GitHubTeamMember_pkey" PRIMARY KEY ("userId")
);
