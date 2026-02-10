import { PrismaPg } from "@prisma/adapter-pg";
import * as dotenv from "dotenv";

import { PrismaClient } from "@/generated/prisma/client";

dotenv.config({ path: ".env.local", quiet: true }); // ← load variables first

// Create a singleton Prisma client instance
const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

function createPrismaClient() {
  const adapter = new PrismaPg({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false },
  });
  return new PrismaClient({ adapter });
}

export const prisma = globalForPrisma.prisma ?? createPrismaClient();

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
