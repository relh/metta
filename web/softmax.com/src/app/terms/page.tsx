import { Container } from "@/components/Container";

import TermsOfService from "./terms-of-service.mdx";

export const metadata = {
  title: "Softmax - Terms of Service",
};

export default function TermsPage() {
  return (
    <div className="flex w-full flex-col items-center">
      <div className="mt-8 mb-24 w-full max-w-[1200px] rounded-sm bg-[#fffdf4]">
        <Container>
          <TermsOfService />
        </Container>
      </div>
    </div>
  );
}
