"use client";

import { agentsApi, ApiClientError } from "@jkr/sdk";
import { Button, useToast } from "@jkr/ui";
import { Bot, Calendar, Headphones, HelpCircle, MessageSquare, PhoneCall, Sparkles, TrendingUp, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

interface AgentPromptCreatorProps {
  workspaceId: string;
}

interface CategoryTemplate {
  id: string;
  label: string;
  icon: React.ElementType;
  defaultName: string;
  defaultBiz: string;
  templateKey: string;
  language: string;
  prompt: string;
}

const CATEGORIES: CategoryTemplate[] = [
  {
    id: "lead_qualification",
    label: "Lead Qualification",
    icon: TrendingUp,
    defaultName: "Real Estate Sales Qualifier",
    defaultBiz: "Hyderabad Prime Properties",
    templateKey: "sales_qualifier",
    language: "te-en-IN",
    prompt:
      "Create a professional Telugu-English sales qualifier agent for a real estate agency in Hyderabad to verify buyer budget, BHK preferences (2BHK / 3BHK), and schedule an in-person site visit.",
  },
  {
    id: "appointments",
    label: "Appointments",
    icon: Calendar,
    defaultName: "Aaha Dental Appointment Coordinator",
    defaultBiz: "Aaha Dental Care",
    templateKey: "appointment_coordinator",
    language: "te-en-IN",
    prompt:
      "Create a warm, polite receptionist agent for Aaha Dental Clinic who speaks in Telugu and English, confirms doctor appointments, handles rescheduling requests, and gives clinic timings.",
  },
  {
    id: "support",
    label: "Customer Support",
    icon: Headphones,
    defaultName: "Customer Support Specialist",
    defaultBiz: "FastKart Retail",
    templateKey: "warm_receptionist",
    language: "te-en-IN",
    prompt:
      "Create an empathetic 24/7 customer service voice agent for a retail brand to answer delivery inquiries, explain return policies, and gracefully escalate complex issues to human agents.",
  },
  {
    id: "collections",
    label: "Payment & Collections",
    icon: PhoneCall,
    defaultName: "EMI & Payment Reminder Agent",
    defaultBiz: "SecureFinance India",
    templateKey: "retention_specialist",
    language: "te-en-IN",
    prompt:
      "Create a courteous finance reminder voice agent to respectfully remind customers about upcoming EMI dues, share UPI payment steps, and confirm expected payment dates.",
  },
  {
    id: "feedback",
    label: "Feedback & Follow-up",
    icon: MessageSquare,
    defaultName: "Service Quality Follow-up",
    defaultBiz: "Apex Motors Service",
    templateKey: "warm_receptionist",
    language: "te-en-IN",
    prompt:
      "Create a friendly post-service follow-up assistant for an automobile garage to ask customers about their vehicle repair experience, collect rating scores, and log suggestions.",
  },
];

export function AgentPromptCreator({ workspaceId }: AgentPromptCreatorProps) {
  const router = useRouter();
  const { toast } = useToast();

  const [prompt, setPrompt] = React.useState("");
  const [selectedCategory, setSelectedCategory] = React.useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  const charLimit = 1200;

  const handleSelectCategory = (cat: CategoryTemplate) => {
    setSelectedCategory(cat.id);
    setPrompt(cat.prompt);
  };

  const handleCreateAgent = async () => {
    if (!prompt.trim()) {
      toast({
        title: "Please describe your assistant",
        description: "Type a prompt or click one of the quick categories below.",
        variant: "danger",
      });
      return;
    }

    setIsSubmitting(true);
    try {
      // Find matching category or synthesize smart defaults from text
      const matchedCat = CATEGORIES.find((c) => c.id === selectedCategory);
      let name = matchedCat?.defaultName || "Custom AI Calling Agent";
      let business = matchedCat?.defaultBiz || "My Business";
      let template = matchedCat?.templateKey || "warm_receptionist";
      let language = matchedCat?.language || "te-en-IN";

      const lowerPrompt = prompt.toLowerCase();
      if (lowerPrompt.includes("dental") || lowerPrompt.includes("clinic") || lowerPrompt.includes("doctor")) {
        business = "Aaha Dental Care";
        name = "Dental Appointment Coordinator";
        template = "appointment_coordinator";
      } else if (lowerPrompt.includes("real estate") || lowerPrompt.includes("property") || lowerPrompt.includes("sales")) {
        business = "Hyderabad Properties";
        name = "Property Sales Qualifier";
        template = "sales_qualifier";
      } else if (lowerPrompt.includes("emi") || lowerPrompt.includes("payment") || lowerPrompt.includes("due")) {
        business = "Finance Services";
        name = "Payment Reminder Agent";
        template = "retention_specialist";
      }

      const agent = await agentsApi.create(workspaceId, {
        name,
        business_identity: business,
        description: prompt.slice(0, 500),
        persona_template: template,
        primary_language: language,
      });

      toast({
        title: "Assistant Created! 🎉",
        description: `Created "${name}" with starter persona and Telugu-English configuration.`,
        variant: "success",
      });

      router.push(`/app/agents/${agent.id}`);
      router.refresh();
    } catch (err) {
      toast({
        title: "Could not create assistant",
        description: err instanceof ApiClientError ? err.message : "An error occurred while creating the agent.",
        variant: "danger",
      });
      setIsSubmitting(false);
    }
  };

  const handleOpenManualWizard = () => {
    const query = new URLSearchParams();
    if (prompt.trim()) query.set("prompt", prompt.trim());
    if (selectedCategory) query.set("category", selectedCategory);
    router.push(`/app/agents/new?${query.toString()}`);
  };

  return (
    <div className="rounded-2xl border border-primary/30 bg-surface-raised p-5 shadow-lg transition-all duration-200 hover:border-primary/50 sm:p-6">
      {/* Header */}
      <div className="mb-3">
        <h2 className="text-base font-bold tracking-tight text-foreground sm:text-lg flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <span>Create a new voice AI assistant</span>
        </h2>
        <p className="text-xs text-muted-foreground sm:text-sm">
          Describe the type of voice AI assistant you want to create — our model configures persona, greeting, and Telugu-English voice parameters instantly.
        </p>
      </div>

      {/* Main Textarea */}
      <div className="relative mb-3">
        <textarea
          value={prompt}
          onChange={(e) => {
            if (e.target.value.length <= charLimit) {
              setPrompt(e.target.value);
            }
          }}
          placeholder="Describe your ideal Voice AI assistant (e.g. A polite bilingual receptionist for my clinic who can qualify patient inquiries and confirm appointment slots in Telugu and English)..."
          rows={4}
          className="w-full resize-none rounded-xl border border-border/80 bg-surface p-4 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary shadow-inner"
        />
        {/* Character Counter */}
        <div className="absolute bottom-3 right-4 font-mono text-[11px] text-muted-foreground">
          {prompt.length}/{charLimit}
        </div>
      </div>

      {/* Quick Use Case Category Buttons */}
      <div className="mb-4">
        <p className="mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Choose from Use Case Categories:
        </p>
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((cat) => {
            const Icon = cat.icon;
            const isSelected = selectedCategory === cat.id;

            return (
              <button
                key={cat.id}
                type="button"
                onClick={() => handleSelectCategory(cat)}
                className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all duration-150 ${
                  isSelected
                    ? "border-primary bg-primary/15 text-primary shadow-sm"
                    : "border-border/80 bg-surface text-muted-foreground hover:border-border hover:bg-surface/80 hover:text-foreground"
                }`}
              >
                <Icon className={`h-3.5 w-3.5 ${isSelected ? "text-primary" : "text-muted-foreground"}`} />
                <span>{cat.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Actions Strip */}
      <div className="flex flex-col-reverse items-center justify-between gap-3 sm:flex-row">
        <button
          type="button"
          onClick={handleOpenManualWizard}
          className="text-xs text-muted-foreground hover:text-primary transition-colors underline-offset-4 hover:underline"
        >
          Or configure manually in step-by-step wizard →
        </button>

        <Button
          type="button"
          onClick={handleCreateAgent}
          loading={isSubmitting}
          disabled={!prompt.trim()}
          variant="gradient"
          className="w-full sm:w-auto font-bold px-6"
        >
          <Bot className="mr-1.5 h-4 w-4" />
          Create Voice AI Assistant
        </Button>
      </div>
    </div>
  );
}
