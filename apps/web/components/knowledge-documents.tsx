"use client";

import {
  APPROVAL_STATE_VARIANT,
  type AgentOut,
  type DocumentCreate,
  type DocumentOut,
  SOURCE_TYPE_OPTIONS,
} from "@jkr/contracts";
import { ApiClientError, knowledgeApi } from "@jkr/sdk";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  FieldError,
  Input,
  Label,
  Textarea,
  useToast,
} from "@jkr/ui";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Bot,
  Building2,
  Calendar,
  Check,
  CheckCircle2,
  Clock,
  FileText,
  Globe,
  HelpCircle,
  Languages,
  Loader2,
  MapPin,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Trash2,
  Upload,
  UserCheck,
  Users,
  Wand2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.split(",")[1] ?? "");
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// ---------------------------------------------------------------------------
// Guided Questionnaire Types & Preset Templates
// ---------------------------------------------------------------------------

interface QuestionnaireAnswers {
  business_name?: string;
  business_type?: string;
  what_we_offer?: string;
  why_choose_us?: string;
  team_languages?: string;
  city?: string;
  state?: string;
  full_address?: string;
  landmark?: string;
  google_maps_url?: string;
  service_area?: string;
  working_days_and_hours?: string;
  phone?: string;
  whatsapp?: string;
  email?: string;
  website?: string;
  top_products_or_services?: { name: string; price: string; description: string }[];
  offers_and_discounts?: string;
  payment_methods?: string;
  delivery_and_shipping?: string;
  returns_refunds_cancellation?: string;
  // Category-specific
  available_slots?: string;
  booking_rules?: string;
  rescheduling_no_show_policy?: string;
  doctor_or_staff_names?: string;
  ideal_customer?: string;
  budget_range?: string;
  hot_lead_criteria?: string;
  common_issues_and_fixes?: string;
  warranty_terms?: string;
  due_date_rules?: string;
  late_fee_policy?: string;
  rating_scale?: string;
  negative_feedback_protocol?: string;
  // FAQs & Guardrails
  customer_faqs?: { question: string; answer: string }[];
  guardrails?: string;
  human_escalation?: string;
}

const PRESET_CLOTHING_STORE: QuestionnaireAnswers = {
  business_name: "Crazy Cloths",
  business_type: "clothing_store",
  what_we_offer: "Premium festive ethnic wear, designer sarees, silk kurtas, bridal lehengas, and daily cotton menswear.",
  why_choose_us: "100% pure handloom fabrics directly sourced from weavers, in-house custom alterations in 2 hours, transparent pricing.",
  team_languages: "Telugu, Hindi, English",
  city: "Hyderabad",
  state: "Telangana",
  full_address: "Plot 42, Road No 36, Jubilee Hills, Hyderabad, Telangana 500033",
  landmark: "Near Peddamma Temple Metro Station",
  google_maps_url: "https://maps.google.com/?q=Crazy+Cloths+Jubilee+Hills",
  service_area: "In-store walk-ins across Hyderabad, plus Pan-India shipping for online/WhatsApp orders.",
  working_days_and_hours: "Monday to Sunday, 10:00 AM to 09:30 PM (Open on all public holidays)",
  phone: "+91 98480 12345",
  whatsapp: "+91 98480 12345",
  email: "care@crazycloths.in",
  website: "https://crazycloths.in",
  top_products_or_services: [
    { name: "Kanjeevaram Pure Silk Sarees", price: "₹6,999 - ₹45,000", description: "Authentic silk-mark certified sarees with rich zari pallu" },
    { name: "Men's Festive Kurta Pajama Sets", price: "₹1,899 - ₹5,499", description: "Linen, silk-blend, and embroidered festive kurtas" },
    { name: "Bridal & Party Wear Lehengas", price: "₹12,500 - ₹85,000", description: "Custom-fitted designer lehengas with cancan support" },
    { name: "Pure Cotton Casual Shirts & Kurtas", price: "₹899 - ₹1,899", description: "Breathable daily wear cotton shirts for men and women" },
  ],
  offers_and_discounts: "Flat 15% off on bridal lehengas during wedding season. Buy 2 Get 1 Free on cotton casual wear.",
  payment_methods: "UPI (Google Pay, PhonePe, Paytm), Cash on Delivery (COD in Hyderabad), Credit & Debit Cards, No-Cost EMI on transactions above ₹10,000.",
  delivery_and_shipping: "Same-day delivery in Hyderabad via Porter/Dunzo (₹99 or free on orders above ₹2,000). 3-5 days across India via BlueDart.",
  returns_refunds_cancellation: "7-day exchange or store credit for unworn garments with original tags attached. Custom stitched or altered items cannot be returned. Refunds processed to original payment method within 48 hours of inspection.",
  customer_faqs: [
    { question: "Do you provide custom stitching or alterations?", answer: "Yes! We have an in-house master tailor. Basic alterations take 2 hours; custom stitching takes 3-4 days." },
    { question: "Where is Crazy Cloths located?", answer: "We are on Road No 36, Jubilee Hills, Hyderabad, just 200 meters from the Peddamma Temple Metro Station." },
    { question: "What are your store hours?", answer: "We are open all 7 days from 10:00 AM to 9:30 PM." },
    { question: "Can I return a saree if the color looks different at home?", answer: "Yes, you can exchange it within 7 days with the original tags intact." },
  ],
  guardrails: "Never promise unapproved discounts beyond 15%. Never guarantee 1-hour tailoring without checking with the in-house master. Never share internal wholesale supplier names.",
  human_escalation: "Escalate immediately to Store Manager Rajesh (+91 98480 12346) if a customer has an urgent bridal fitting or complaint.",
};

const PRESET_DENTAL_CLINIC: QuestionnaireAnswers = {
  business_name: "Smile Dental Clinic & Implant Center",
  business_type: "dental_clinic",
  what_we_offer: "Painless root canal treatment, dental implants, teeth whitening, invisible aligners, pediatric dentistry, and dental cleaning.",
  why_choose_us: "Over 15 years experience, US-certified sterilization standards, painless laser technology, and flexible 0% interest EMI options.",
  team_languages: "Telugu, Hindi, English",
  city: "Visakhapatnam",
  state: "Andhra Pradesh",
  full_address: "Door No 10-2-45, 1st Floor, Siripuram Towers, Siripuram Junction, Visakhapatnam 530003",
  landmark: "Opposite HSBC Bank, above Apollo Pharmacy",
  google_maps_url: "https://maps.google.com/?q=Smile+Dental+Siripuram+Vizag",
  service_area: "Visakhapatnam and surrounding coastal Andhra districts.",
  working_days_and_hours: "Monday to Saturday: 09:30 AM to 08:30 PM; Sunday: 10:00 AM to 01:30 PM (Emergency appointments only).",
  phone: "+91 891 254 7890",
  whatsapp: "+91 99660 78901",
  email: "appointments@smiledentalvizag.com",
  website: "https://smiledentalvizag.com",
  top_products_or_services: [
    { name: "Single-Sitting Root Canal (RCT)", price: "₹3,500 - ₹5,500", description: "Painless computerized rotary RCT including digital X-ray" },
    { name: "Zirconia / Ceramic Dental Crown", price: "₹4,000 - ₹12,000", description: "10-year warranty metal-free natural looking crown" },
    { name: "Titanium Dental Implant", price: "₹22,000 - ₹38,000", description: "Lifetime warranty Swiss/German dental implant fixture" },
    { name: "Ultrasonic Teeth Scaling & Polishing", price: "₹1,200 - ₹1,800", description: "Deep cleaning to remove plaque, stains, and tartar" },
  ],
  available_slots: "Morning: 10:00 AM - 01:00 PM; Evening: 04:30 PM - 08:00 PM in 30-minute intervals.",
  booking_rules: "Prior phone appointment recommended to avoid wait times. Walk-ins accepted based on doctor availability.",
  rescheduling_no_show_policy: "Patients can reschedule up to 2 hours before the slot with no fee. No advance deposit required for general consultations.",
  doctor_or_staff_names: "Dr. K. Srinivas Rao (MDS - Endodontist, 16 yrs exp), Dr. P. Ananya (BDS - Cosmetic & Pediatric Dentist)",
  offers_and_discounts: "Free consultation and digital OPG X-ray with any root canal or implant procedure. 10% senior citizen concession on denture treatments.",
  payment_methods: "UPI, Cards, Cash, Bajaj Finserv Health EMI, 0% interest monthly installments for implants & aligners.",
  returns_refunds_cancellation: "Consultation fees are non-refundable after examination. Treatment package cancellations are refunded pro-rata for unused procedures within 7 days.",
  customer_faqs: [
    { question: "Is root canal treatment painful?", answer: "No, we use painless local anesthesia and computerized rotary tools. Most patients feel no pain during or after." },
    { question: "How much does a dental implant cost?", answer: "Implant costs range from ₹22,000 to ₹38,000 depending on the implant brand (Swiss or German) and crown type." },
    { question: "Do you open on Sundays?", answer: "Yes, we are open on Sundays from 10:00 AM to 01:30 PM for emergency cases by prior appointment." },
    { question: "Are Sunday appointments available with Dr. Rao?", answer: "Sunday appointments are reserved for emergency treatments. Please call our clinic directly to confirm Dr. Rao's availability." },
  ],
  guardrails: "NEVER prescribe antibiotics or specific painkillers over the phone. Never guarantee treatment outcome without physical in-person X-ray and examination. Never perform emergency triage without doctor handover.",
  human_escalation: "Escalate immediately to Front Desk Clinic Head Sunitha (+91 99660 78902) or on-duty emergency doctor if the patient has severe acute dental trauma or swelling.",
};

// ---------------------------------------------------------------------------
// Health Score Helper
// ---------------------------------------------------------------------------

function computeLocalHealthScore(answers: QuestionnaireAnswers): {
  score: number;
  missing: string[];
  suggestions: string[];
} {
  let score = 0;
  const missing: string[] = [];
  const suggestions: string[] = [];

  if (answers.business_name && answers.what_we_offer) {
    score += 15;
  } else {
    missing.push("Business name & overview");
    suggestions.push("Add business name and what you offer");
  }

  if (answers.city && answers.full_address) {
    score += 15;
  } else {
    missing.push("Full address & city");
    suggestions.push("Add complete address and city");
  }

  if (answers.working_days_and_hours) {
    score += 10;
  } else {
    missing.push("Operating hours");
    suggestions.push("Specify working days and hours");
  }

  if (answers.top_products_or_services && answers.top_products_or_services.length >= 1) {
    score += answers.top_products_or_services.length >= 3 ? 20 : 12;
  } else {
    missing.push("Products/services with prices");
    suggestions.push("List at least 3 products with prices");
  }

  if (answers.payment_methods) {
    score += 10;
  } else {
    missing.push("Payment methods (UPI, Cards, COD)");
    suggestions.push("Add accepted payment methods");
  }

  if (answers.returns_refunds_cancellation || answers.rescheduling_no_show_policy) {
    score += 15;
  } else {
    missing.push("Returns or cancellation policy");
    suggestions.push("Add return/cancellation policy");
  }

  if (answers.customer_faqs && answers.customer_faqs.length >= 2) {
    score += 10;
  } else {
    missing.push("Top customer FAQs");
    suggestions.push("Add at least 3 common customer questions");
  }

  if (answers.guardrails && answers.human_escalation) {
    score += 10;
  } else {
    missing.push("AI guardrails & human escalation");
    suggestions.push("Set what AI must never say and escalation contact");
  }

  return { score: Math.min(100, score), missing, suggestions };
}

// ---------------------------------------------------------------------------
// Main KnowledgeDocuments Component
// ---------------------------------------------------------------------------

export function KnowledgeDocuments({
  workspaceId,
  documents: initialDocuments,
  agents = [],
  initialAgentId,
}: {
  workspaceId: string;
  documents: DocumentOut[];
  agents?: AgentOut[];
  initialAgentId?: string;
}) {
  const router = useRouter();
  const { toast } = useToast();

  // Active agent selection & scoping
  const [selectedAgentId, setSelectedAgentId] = React.useState<string>(initialAgentId || "all");
  const [documents, setDocuments] = React.useState<DocumentOut[]>(initialDocuments);

  // Tab: "guided" | "text" | "upload"
  const [activeTab, setActiveTab] = React.useState<"guided" | "text" | "upload">("guided");

  // Questionnaire Wizard state
  const [wizardStep, setWizardStep] = React.useState<number>(1);
  const [wizardLanguage, setWizardLanguage] = React.useState<"en" | "te" | "hi">("en");
  const [answers, setAnswers] = React.useState<QuestionnaireAnswers>(() => {
    // Autosave restoration from localStorage
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem(`jkr_kb_draft_${workspaceId}_${initialAgentId || "all"}`);
        if (saved) return JSON.parse(saved);
      } catch {}
    }
    // Prefill from selected agent if available
    const activeAgent = agents.find((a) => a.id === initialAgentId);
    return {
      business_name: activeAgent?.name ?? "",
      business_type: activeAgent?.persona_template ?? "clothing_store",
      team_languages: "Telugu, Hindi, English",
    };
  });

  // Autosave to localStorage
  React.useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem(`jkr_kb_draft_${workspaceId}_${selectedAgentId}`, JSON.stringify(answers));
      } catch {}
    }
  }, [answers, workspaceId, selectedAgentId]);

  // AI Generated preview state
  const [generating, setGenerating] = React.useState<boolean>(false);
  const [generatedDoc, setGeneratedDoc] = React.useState<{
    title: string;
    text: string;
    health_score: number;
    missing_fields: string[];
    suggestions: string[];
  } | null>(null);
  const [assignScope, setAssignScope] = React.useState<"workspace" | "agent">(
    selectedAgentId !== "all" ? "agent" : "workspace"
  );
  const [approving, setApproving] = React.useState<boolean>(false);

  // Filter documents based on selected agent
  const filteredDocuments = React.useMemo(() => {
    if (selectedAgentId === "all") return documents;
    return documents.filter((d) => d.scope === "workspace" || (d.agent_ids && d.agent_ids.includes(selectedAgentId)));
  }, [documents, selectedAgentId]);

  // In-page "Ask your agent" tester state
  const [testQuery, setTestQuery] = React.useState<string>("");
  const [testLoading, setTestLoading] = React.useState<boolean>(false);
  const [testResponse, setTestResponse] = React.useState<{
    answer: string;
    grounded: boolean;
    matched_chunks: any[];
    used_scope: string;
    latency_ms: Record<string, number>;
  } | null>(null);

  // Health score calculation
  const healthInfo = React.useMemo(() => computeLocalHealthScore(answers), [answers]);

  // Helper to load presets
  const applyPreset = (preset: QuestionnaireAnswers) => {
    setAnswers(preset);
    toast({
      title: `✨ Loaded ${preset.business_name} Template`,
      description: "Questionnaire pre-filled with comprehensive, realistic answers. Click Next or Generate!",
      variant: "success",
    });
  };

  // Generate Knowledge with AI
  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const activeAgent = agents.find((a) => a.id === selectedAgentId);
      const res = await knowledgeApi.generateFromAnswers(workspaceId, {
        business_type: answers.business_type || "general",
        agent_category: activeAgent?.persona_template || activeAgent?.description || "general",
        language: wizardLanguage,
        agent_id: selectedAgentId !== "all" ? selectedAgentId : undefined,
        answers: answers as Record<string, any>,
      });

      setGeneratedDoc({
        title: res.title,
        text: res.generated_text,
        health_score: res.health_score,
        missing_fields: res.missing_fields,
        suggestions: res.suggestions,
      });

      toast({
        title: "✨ Grounded Knowledge Generated!",
        description: `Score: ${res.health_score}% complete. Review the preview below and click 'Approve & Index'.`,
        variant: "success",
      });
    } catch (err) {
      toast({
        title: "Generation failed",
        description: err instanceof ApiClientError ? err.message : "Could not generate knowledge.",
        variant: "danger",
      });
    } finally {
      setGenerating(false);
    }
  };

  // Approve & Index Generated Document
  const handleApproveAndIndex = async () => {
    if (!generatedDoc) return;
    setApproving(true);
    try {
      const agentIds = assignScope === "agent" && selectedAgentId !== "all" ? [selectedAgentId] : [];
      // 1. Create document
      const doc = await knowledgeApi.createDocument(workspaceId, {
        source_type: "manual_faq",
        title: generatedDoc.title,
        scope: assignScope,
        agent_ids: agentIds,
        language: wizardLanguage === "en" ? "en-IN" : wizardLanguage === "te" ? "te-IN" : "hi-IN",
        raw_text: generatedDoc.text,
      });

      // 2. Process (chunk & embed)
      await knowledgeApi.processDocument(workspaceId, doc.id);

      // 3. Approve immediately
      const approvedDoc = await knowledgeApi.approveDocument(workspaceId, doc.id, "Approved via AI Knowledge Builder");

      toast({
        title: "🎉 Knowledge Approved & Indexed!",
        description: `Your agents can now recite this knowledge during live phone calls! (Scope: ${assignScope})`,
        variant: "success",
      });

      setDocuments((prev) => [approvedDoc, ...prev]);
      setGeneratedDoc(null);
      router.refresh();
    } catch (err) {
      toast({
        title: "Approval failed",
        description: err instanceof ApiClientError ? err.message : "Could not approve document.",
        variant: "danger",
      });
    } finally {
      setApproving(false);
    }
  };

  // Run in-page agent test
  const handleTestAgent = async () => {
    if (!testQuery.trim()) return;
    setTestLoading(true);
    try {
      const res = await knowledgeApi.testAgent(workspaceId, {
        query: testQuery,
        agent_id: selectedAgentId !== "all" ? selectedAgentId : undefined,
        language: wizardLanguage,
      });
      setTestResponse(res);
    } catch (err) {
      toast({
        title: "Test query failed",
        description: err instanceof ApiClientError ? err.message : "Error executing RAG search.",
        variant: "danger",
      });
    } finally {
      setTestLoading(false);
    }
  };

  // Switch agent and update scope
  const handleAgentChange = (newAgentId: string) => {
    setSelectedAgentId(newAgentId);
    setAssignScope(newAgentId === "all" ? "workspace" : "agent");
    setTestResponse(null);
  };

  const selectedAgent = agents.find((a) => a.id === selectedAgentId);

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------------------------- */}
      {/* 1. Explainer Card & Agent Picker Header                             */}
      {/* ------------------------------------------------------------------- */}
      <Card className="border-primary/20 bg-primary/5">
        <CardHeader className="pb-3">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-primary animate-pulse" />
                <CardTitle className="text-lg font-bold">Smart Knowledge Builder &amp; Agent Scope</CardTitle>
              </div>
              <CardDescription className="text-xs text-muted-foreground">
                <strong>What it is:</strong> Ground truth business knowledge your AI agents recite accurately during phone calls.
                <br />
                <strong>Why we use it:</strong> Eliminates hallucinations, guarantees truthful pricing/location details, and enforces strict per-agent tenant isolation.
              </CardDescription>
            </div>

            {/* Agent Picker Dropdown */}
            <div className="flex items-center gap-3 bg-surface p-2.5 rounded-xl border border-border shadow-sm">
              <Bot className="h-4 w-4 text-primary shrink-0" />
              <div className="space-y-0.5">
                <Label htmlFor="agent-picker" className="text-[11px] font-semibold text-muted-foreground">
                  Select Target Agent:
                </Label>
                <select
                  id="agent-picker"
                  value={selectedAgentId}
                  onChange={(e) => handleAgentChange(e.target.value)}
                  className="bg-transparent text-xs font-bold text-foreground focus:outline-none cursor-pointer"
                >
                  <option value="all">🌐 All Workspace Agents (Workspace-Wide)</option>
                  {agents.map((ag) => (
                    <option key={ag.id} value={ag.id}>
                      🤖 {ag.name} ({ag.persona_template ?? "Standard"})
                    </option>
                  ))}
                </select>
              </div>
              <Badge variant={selectedAgentId === "all" ? "secondary" : "default"} className="shrink-0 text-[10px]">
                {selectedAgentId === "all" ? "Workspace Scope" : "Agent Scoped"}
              </Badge>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* ------------------------------------------------------------------- */}
      {/* 2. Knowledge Health Score Card                                      */}
      {/* ------------------------------------------------------------------- */}
      <Card className="border-border">
        <CardContent className="pt-5 pb-5">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1.5 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-foreground">Knowledge Health Score</span>
                <Badge
                  variant={
                    healthInfo.score >= 80 ? "success" : healthInfo.score >= 50 ? "warning" : "danger"
                  }
                  className="font-bold text-xs"
                >
                  {healthInfo.score}% Complete
                </Badge>
                {healthInfo.score >= 80 ? (
                  <span className="text-xs text-emerald-500 font-medium flex items-center gap-1">
                    <CheckCircle2 className="h-3.5 w-3.5" /> Ready for live calls
                  </span>
                ) : (
                  <span className="text-xs text-amber-500 font-medium flex items-center gap-1">
                    <AlertCircle className="h-3.5 w-3.5" /> Needs more details before taking live calls
                  </span>
                )}
              </div>

              {/* Visual Health Bar */}
              <div className="w-full bg-surface-raised rounded-full h-2.5 overflow-hidden border border-border/60">
                <div
                  className={`h-full transition-all duration-500 rounded-full ${
                    healthInfo.score >= 80
                      ? "bg-emerald-500"
                      : healthInfo.score >= 50
                      ? "bg-amber-500"
                      : "bg-red-500"
                  }`}
                  style={{ width: `${healthInfo.score}%` }}
                />
              </div>

              {/* Suggestions */}
              {healthInfo.suggestions.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <span className="text-[11px] text-muted-foreground font-semibold">One-Click Suggestions:</span>
                  {healthInfo.suggestions.slice(0, 3).map((sug, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => {
                        setActiveTab("guided");
                        setWizardStep(idx === 0 ? 1 : idx === 1 ? 2 : 4);
                      }}
                      className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full bg-surface-raised hover:bg-primary/10 hover:text-primary transition-colors border border-border text-foreground"
                    >
                      <Plus className="h-3 w-3" />
                      {sug}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Quick Template Buttons */}
            <div className="flex flex-wrap items-center gap-2 shrink-0 border-t md:border-t-0 md:border-l border-border pt-3 md:pt-0 md:pl-4">
              <span className="text-[11px] text-muted-foreground font-medium block w-full md:w-auto">
                Test with 1-Click Template:
              </span>
              <Button
                size="sm"
                variant="secondary"
                className="text-xs font-semibold h-8"
                onClick={() => applyPreset(PRESET_CLOTHING_STORE)}
              >
                👗 Crazy Cloths (Store)
              </Button>
              <Button
                size="sm"
                variant="secondary"
                className="text-xs font-semibold h-8"
                onClick={() => applyPreset(PRESET_DENTAL_CLINIC)}
              >
                🦷 Dental Clinic
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ------------------------------------------------------------------- */}
      {/* 3. Three Ways to Add Knowledge (Tabs)                                */}
      {/* ------------------------------------------------------------------- */}
      <div className="flex items-center gap-2 border-b border-border pb-2">
        <button
          type="button"
          onClick={() => setActiveTab("guided")}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-bold rounded-lg transition-all ${
            activeTab === "guided"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-surface-raised"
          }`}
        >
          <Wand2 className="h-4 w-4" />
          Guided Questions (AI Generates It)
          <span className="text-[10px] bg-white/20 px-1.5 py-0.5 rounded-full font-normal">Recommended</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("text")}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-bold rounded-lg transition-all ${
            activeTab === "text"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-surface-raised"
          }`}
        >
          <FileText className="h-4 w-4" />
          Write or Paste Text
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("upload")}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-bold rounded-lg transition-all ${
            activeTab === "upload"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-surface-raised"
          }`}
        >
          <Upload className="h-4 w-4" />
          Upload Files &amp; Website URL
        </button>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* TAB 1: Guided Questions (AI Builder Wizard)                         */}
      {/* ------------------------------------------------------------------- */}
      {activeTab === "guided" && (
        <Card className="border-border">
          <CardHeader className="pb-3 border-b border-border">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <CardTitle className="text-base font-bold flex items-center gap-2">
                  <span>Step {wizardStep} of 6:</span>
                  {wizardStep === 1 && "Business Identity & Overview"}
                  {wizardStep === 2 && "Location, Working Hours & Contact"}
                  {wizardStep === 3 && "Top Products / Services & Pricing"}
                  {wizardStep === 4 && "Offers, Payment Methods & Delivery Policies"}
                  {wizardStep === 5 && "Category Specifics (Appointments, Leads, Support)"}
                  {wizardStep === 6 && "Customer FAQs, AI Guardrails & Escalation"}
                </CardTitle>
                <CardDescription className="text-xs">
                  Skippable fields. Only your real answers will be used. Missing details are marked &quot;Not provided&quot;.
                </CardDescription>
              </div>

              {/* Language Switcher */}
              <div className="flex items-center gap-1.5 bg-surface-raised p-1 rounded-lg border border-border">
                <Languages className="h-3.5 w-3.5 text-muted-foreground ml-1" />
                {(["en", "te", "hi"] as const).map((lang) => (
                  <button
                    key={lang}
                    type="button"
                    onClick={() => setWizardLanguage(lang)}
                    className={`text-xs px-2.5 py-1 rounded font-semibold transition-colors ${
                      wizardLanguage === lang
                        ? "bg-primary text-primary-foreground shadow-xs"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {lang === "en" ? "English" : lang === "te" ? "తెలుగు" : "हिन्दी"}
                  </button>
                ))}
              </div>
            </div>

            {/* Step Progress Line */}
            <div className="grid grid-cols-6 gap-2 pt-3">
              {[1, 2, 3, 4, 5, 6].map((s) => (
                <div
                  key={s}
                  onClick={() => setWizardStep(s)}
                  className={`h-1.5 rounded-full cursor-pointer transition-all ${
                    s === wizardStep
                      ? "bg-primary"
                      : s < wizardStep
                      ? "bg-emerald-500"
                      : "bg-surface-raised border border-border"
                  }`}
                />
              ))}
            </div>
          </CardHeader>

          <CardContent className="pt-6 space-y-5">
            {/* Step 1: Business Identity */}
            {wizardStep === 1 && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="q-biz-name">Business Name *</Label>
                    <Input
                      id="q-biz-name"
                      value={answers.business_name ?? ""}
                      onChange={(e) => setAnswers({ ...answers, business_name: e.target.value })}
                      placeholder="e.g. Crazy Cloths, Smile Dental Clinic"
                    />
                  </div>
                  <div>
                    <Label htmlFor="q-biz-type">Business Type / Industry</Label>
                    <select
                      id="q-biz-type"
                      value={answers.business_type ?? "clothing_store"}
                      onChange={(e) => setAnswers({ ...answers, business_type: e.target.value })}
                      className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
                    >
                      <option value="clothing_store">Clothing &amp; Fashion Store</option>
                      <option value="dental_clinic">Dental Clinic &amp; Healthcare</option>
                      <option value="restaurant">Restaurant &amp; Food Delivery</option>
                      <option value="real_estate">Real Estate &amp; Property</option>
                      <option value="salon">Salon, Beauty &amp; Spa</option>
                      <option value="consulting">Consulting &amp; Professional Services</option>
                      <option value="other">Other Business</option>
                    </select>
                  </div>
                </div>

                <div>
                  <Label htmlFor="q-what-offer">What do you sell or offer? *</Label>
                  <Textarea
                    id="q-what-offer"
                    rows={2}
                    value={answers.what_we_offer ?? ""}
                    onChange={(e) => setAnswers({ ...answers, what_we_offer: e.target.value })}
                    placeholder="e.g. Festive ethnic wear, pure silk sarees, designer kurtas, bridal lehengas..."
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="q-why-us">Why do customers choose you? (Differentiators)</Label>
                    <Input
                      id="q-why-us"
                      value={answers.why_choose_us ?? ""}
                      onChange={(e) => setAnswers({ ...answers, why_choose_us: e.target.value })}
                      placeholder="e.g. 100% handloom certified, 2-hour alterations, 15 yrs experience..."
                    />
                  </div>
                  <div>
                    <Label htmlFor="q-team-lang">Languages spoken by your staff</Label>
                    <Input
                      id="q-team-lang"
                      value={answers.team_languages ?? ""}
                      onChange={(e) => setAnswers({ ...answers, team_languages: e.target.value })}
                      placeholder="e.g. Telugu, Hindi, English"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Step 2: Location & Operating Hours */}
            {wizardStep === 2 && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="q-city">City *</Label>
                    <Input
                      id="q-city"
                      value={answers.city ?? ""}
                      onChange={(e) => setAnswers({ ...answers, city: e.target.value })}
                      placeholder="e.g. Hyderabad, Visakhapatnam, Vijayawada, Bangalore"
                    />
                  </div>
                  <div>
                    <Label htmlFor="q-state">State</Label>
                    <Input
                      id="q-state"
                      value={answers.state ?? ""}
                      onChange={(e) => setAnswers({ ...answers, state: e.target.value })}
                      placeholder="e.g. Telangana, Andhra Pradesh, Karnataka"
                    />
                  </div>
                </div>

                <div>
                  <Label htmlFor="q-address">Full Address *</Label>
                  <Input
                    id="q-address"
                    value={answers.full_address ?? ""}
                    onChange={(e) => setAnswers({ ...answers, full_address: e.target.value })}
                    placeholder="e.g. Plot 42, Road No 36, Jubilee Hills, Hyderabad 500033"
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="q-landmark">Landmark</Label>
                    <Input
                      id="q-landmark"
                      value={answers.landmark ?? ""}
                      onChange={(e) => setAnswers({ ...answers, landmark: e.target.value })}
                      placeholder="e.g. Near Peddamma Temple Metro Station"
                    />
                  </div>
                  <div>
                    <Label htmlFor="q-maps">Google Maps Link</Label>
                    <Input
                      id="q-maps"
                      value={answers.google_maps_url ?? ""}
                      onChange={(e) => setAnswers({ ...answers, google_maps_url: e.target.value })}
                      placeholder="e.g. https://maps.google.com/..."
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="q-hours">Working Days &amp; Hours *</Label>
                    <Input
                      id="q-hours"
                      value={answers.working_days_and_hours ?? ""}
                      onChange={(e) => setAnswers({ ...answers, working_days_and_hours: e.target.value })}
                      placeholder="e.g. Mon-Sun: 10:00 AM - 09:30 PM (All holidays open)"
                    />
                  </div>
                  <div>
                    <Label htmlFor="q-service-area">Service Coverage Area</Label>
                    <Input
                      id="q-service-area"
                      value={answers.service_area ?? ""}
                      onChange={(e) => setAnswers({ ...answers, service_area: e.target.value })}
                      placeholder="e.g. In-store walk-ins across Hyderabad + Pan-India shipping"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <Label htmlFor="q-phone">Contact Phone</Label>
                    <Input
                      id="q-phone"
                      value={answers.phone ?? ""}
                      onChange={(e) => setAnswers({ ...answers, phone: e.target.value })}
                      placeholder="+91 98480 12345"
                    />
                  </div>
                  <div>
                    <Label htmlFor="q-wa">WhatsApp Number</Label>
                    <Input
                      id="q-wa"
                      value={answers.whatsapp ?? ""}
                      onChange={(e) => setAnswers({ ...answers, whatsapp: e.target.value })}
                      placeholder="+91 98480 12345"
                    />
                  </div>
                  <div>
                    <Label htmlFor="q-email">Email / Website</Label>
                    <Input
                      id="q-email"
                      value={answers.email ?? ""}
                      onChange={(e) => setAnswers({ ...answers, email: e.target.value })}
                      placeholder="care@example.com"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Step 3: Top Products & Pricing */}
            {wizardStep === 3 && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <p className="text-xs text-muted-foreground">
                    List top 3 to 5 products or services with their price (or range) and a one-line description.
                  </p>
                  <Button
                    size="sm"
                    variant="secondary"
                    className="h-8 text-xs font-semibold"
                    onClick={() => {
                      const prods = answers.top_products_or_services ?? [];
                      setAnswers({
                        ...answers,
                        top_products_or_services: [...prods, { name: "", price: "", description: "" }],
                      });
                    }}
                  >
                    <Plus className="h-3.5 w-3.5 mr-1" /> Add Product/Service
                  </Button>
                </div>

                {(answers.top_products_or_services ?? []).length === 0 ? (
                  <div className="p-6 text-center border border-dashed border-border rounded-xl">
                    <p className="text-xs text-muted-foreground mb-3">No products listed yet.</p>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        setAnswers({
                          ...answers,
                          top_products_or_services: [
                            { name: "", price: "", description: "" },
                            { name: "", price: "", description: "" },
                          ],
                        })
                      }
                    >
                      <Plus className="h-3.5 w-3.5 mr-1" /> Add First Items
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {(answers.top_products_or_services ?? []).map((prod, idx) => (
                      <div key={idx} className="p-3 bg-surface-raised rounded-xl border border-border space-y-2">
                        <div className="flex items-center justify-between gap-3">
                          <Input
                            placeholder="Product or Service Name (e.g. Silk Saree, Root Canal)"
                            value={prod.name}
                            className="font-medium text-xs h-8"
                            onChange={(e) => {
                              const updated = [...(answers.top_products_or_services ?? [])];
                              const item = updated[idx];
                              if (item) {
                                updated[idx] = { ...item, name: e.target.value };
                                setAnswers({ ...answers, top_products_or_services: updated });
                              }
                            }}
                          />
                          <Input
                            placeholder="Price / Range (e.g. ₹6,999 - ₹45,000)"
                            value={prod.price}
                            className="w-48 text-xs h-8"
                            onChange={(e) => {
                              const updated = [...(answers.top_products_or_services ?? [])];
                              const item = updated[idx];
                              if (item) {
                                updated[idx] = { ...item, price: e.target.value };
                                setAnswers({ ...answers, top_products_or_services: updated });
                              }
                            }}
                          />
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-8 w-8 p-0 text-muted-foreground hover:text-danger"
                            onClick={() => {
                              const updated = (answers.top_products_or_services ?? []).filter((_, i) => i !== idx);
                              setAnswers({ ...answers, top_products_or_services: updated });
                            }}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                        <Input
                          placeholder="One-line description (e.g. Pure handloom silk certified with rich zari work)"
                          value={prod.description}
                          className="text-xs h-8"
                          onChange={(e) => {
                            const updated = [...(answers.top_products_or_services ?? [])];
                            const item = updated[idx];
                            if (item) {
                              updated[idx] = { ...item, description: e.target.value };
                              setAnswers({ ...answers, top_products_or_services: updated });
                            }
                          }}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Step 4: Offers, Payment & Policies */}
            {wizardStep === 4 && (
              <div className="space-y-4">
                <div>
                  <Label htmlFor="q-offers">Special Offers, Discounts &amp; Festival Deals</Label>
                  <Input
                    id="q-offers"
                    value={answers.offers_and_discounts ?? ""}
                    onChange={(e) => setAnswers({ ...answers, offers_and_discounts: e.target.value })}
                    placeholder="e.g. Flat 15% off bridal wear during wedding season, Buy 2 Get 1 Free on cottons"
                  />
                </div>

                <div>
                  <Label htmlFor="q-payment">Accepted Payment Methods *</Label>
                  <Input
                    id="q-payment"
                    value={answers.payment_methods ?? ""}
                    onChange={(e) => setAnswers({ ...answers, payment_methods: e.target.value })}
                    placeholder="e.g. UPI (Google Pay, PhonePe), Cards, Cash on Delivery, No-Cost EMI"
                  />
                </div>

                <div>
                  <Label htmlFor="q-delivery">Delivery &amp; Shipping Policy</Label>
                  <Input
                    id="q-delivery"
                    value={answers.delivery_and_shipping ?? ""}
                    onChange={(e) => setAnswers({ ...answers, delivery_and_shipping: e.target.value })}
                    placeholder="e.g. Same-day delivery in Hyderabad (₹99 or free over ₹2000), 3-5 days Pan-India"
                  />
                </div>

                <div>
                  <Label htmlFor="q-returns">Returns, Refunds &amp; Cancellation Policy *</Label>
                  <Textarea
                    id="q-returns"
                    rows={2}
                    value={answers.returns_refunds_cancellation ?? ""}
                    onChange={(e) => setAnswers({ ...answers, returns_refunds_cancellation: e.target.value })}
                    placeholder="e.g. 7-day exchange with original tags. Stitched/altered items cannot be returned. Refunds in 48 hours."
                  />
                </div>
              </div>
            )}

            {/* Step 5: Category Specifics */}
            {wizardStep === 5 && (
              <div className="space-y-4">
                <div className="p-3 bg-primary/5 rounded-xl border border-primary/20 text-xs text-muted-foreground flex items-center gap-2">
                  <Bot className="h-4 w-4 text-primary shrink-0" />
                  <span>
                    These adaptive fields help your agent answer specific appointment booking, lead qualification, or support workflows seamlessly.
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="q-slots">Available Slots &amp; Timings</Label>
                    <Input
                      id="q-slots"
                      value={answers.available_slots ?? ""}
                      onChange={(e) => setAnswers({ ...answers, available_slots: e.target.value })}
                      placeholder="e.g. 10:00 AM - 01:00 PM and 04:30 PM - 08:00 PM (30 min slots)"
                    />
                  </div>
                  <div>
                    <Label htmlFor="q-booking-rules">Booking Rules &amp; Advance Notice</Label>
                    <Input
                      id="q-booking-rules"
                      value={answers.booking_rules ?? ""}
                      onChange={(e) => setAnswers({ ...answers, booking_rules: e.target.value })}
                      placeholder="e.g. Prior phone appointment recommended, walk-ins accepted"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="q-reschedule">Rescheduling &amp; No-Show Policy</Label>
                    <Input
                      id="q-reschedule"
                      value={answers.rescheduling_no_show_policy ?? ""}
                      onChange={(e) => setAnswers({ ...answers, rescheduling_no_show_policy: e.target.value })}
                      placeholder="e.g. Free rescheduling up to 2 hours before slot"
                    />
                  </div>
                  <div>
                    <Label htmlFor="q-staff">Doctor / Specialist / Staff Names</Label>
                    <Input
                      id="q-staff"
                      value={answers.doctor_or_staff_names ?? ""}
                      onChange={(e) => setAnswers({ ...answers, doctor_or_staff_names: e.target.value })}
                      placeholder="e.g. Dr. K. Srinivas Rao (Endodontist), Master Tailor Rajesh"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="q-ideal">Ideal Customer / Hot Lead Criteria</Label>
                    <Input
                      id="q-ideal"
                      value={answers.hot_lead_criteria ?? ""}
                      onChange={(e) => setAnswers({ ...answers, hot_lead_criteria: e.target.value })}
                      placeholder="e.g. Looking for bridal package, budget > ₹20k, ready to visit this week"
                    />
                  </div>
                  <div>
                    <Label htmlFor="q-issues">Common Support Issues &amp; Fixes</Label>
                    <Input
                      id="q-issues"
                      value={answers.common_issues_and_fixes ?? ""}
                      onChange={(e) => setAnswers({ ...answers, common_issues_and_fixes: e.target.value })}
                      placeholder="e.g. Sizing exchange, tracking delivery delay, emergency toothache"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Step 6: FAQs & Guardrails */}
            {wizardStep === 6 && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label>Top Frequently Asked Questions (Q&amp;A)</Label>
                  <Button
                    size="sm"
                    variant="secondary"
                    className="h-8 text-xs font-semibold"
                    onClick={() => {
                      const faqs = answers.customer_faqs ?? [];
                      setAnswers({
                        ...answers,
                        customer_faqs: [...faqs, { question: "", answer: "" }],
                      });
                    }}
                  >
                    <Plus className="h-3.5 w-3.5 mr-1" /> Add FAQ
                  </Button>
                </div>

                {(answers.customer_faqs ?? []).map((faq, idx) => (
                  <div key={idx} className="p-3 bg-surface-raised rounded-xl border border-border space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <Input
                        placeholder="Customer Question (e.g. Do you open on Sundays?)"
                        value={faq.question}
                        className="text-xs h-8 font-semibold"
                        onChange={(e) => {
                          const updated = [...(answers.customer_faqs ?? [])];
                          const item = updated[idx];
                          if (item) {
                            updated[idx] = { ...item, question: e.target.value };
                            setAnswers({ ...answers, customer_faqs: updated });
                          }
                        }}
                      />
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 w-8 p-0 text-muted-foreground hover:text-danger"
                        onClick={() => {
                          const updated = (answers.customer_faqs ?? []).filter((_, i) => i !== idx);
                          setAnswers({ ...answers, customer_faqs: updated });
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                    <Input
                      placeholder="Direct Phone-Spoken Answer (e.g. Yes, we are open on Sundays from 10 AM to 9:30 PM.)"
                      value={faq.answer}
                      className="text-xs h-8"
                      onChange={(e) => {
                        const updated = [...(answers.customer_faqs ?? [])];
                        const item = updated[idx];
                        if (item) {
                          updated[idx] = { ...item, answer: e.target.value };
                          setAnswers({ ...answers, customer_faqs: updated });
                        }
                      }}
                    />
                  </div>
                ))}

                <div>
                  <Label htmlFor="q-guardrails" className="text-danger flex items-center gap-1.5">
                    <ShieldAlert className="h-3.5 w-3.5" />
                    What must the AI NEVER promise or say? (Guardrails) *
                  </Label>
                  <Textarea
                    id="q-guardrails"
                    rows={2}
                    value={answers.guardrails ?? ""}
                    onChange={(e) => setAnswers({ ...answers, guardrails: e.target.value })}
                    placeholder="e.g. Never prescribe medicines over call. Never offer unapproved discounts beyond 15%. Never give legal or financial guarantees."
                  />
                </div>

                <div>
                  <Label htmlFor="q-escalate">When to hand over to a human, and to whom? *</Label>
                  <Input
                    id="q-escalate"
                    value={answers.human_escalation ?? ""}
                    onChange={(e) => setAnswers({ ...answers, human_escalation: e.target.value })}
                    placeholder="e.g. Transfer to Store Manager Rajesh (+91 98480 12346) if customer has unresolved complaints"
                  />
                </div>
              </div>
            )}

            {/* Wizard Navigation Footer */}
            <div className="flex items-center justify-between pt-4 border-t border-border">
              <Button
                variant="ghost"
                size="sm"
                disabled={wizardStep === 1}
                onClick={() => setWizardStep((prev) => Math.max(1, prev - 1))}
              >
                <ArrowLeft className="h-4 w-4 mr-1.5" /> Previous
              </Button>

              <div className="flex items-center gap-2">
                {wizardStep < 6 ? (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setWizardStep((prev) => Math.min(6, prev + 1))}
                    >
                      Skip this step
                    </Button>
                    <Button
                      variant="default"
                      size="sm"
                      className="font-bold"
                      onClick={() => setWizardStep((prev) => Math.min(6, prev + 1))}
                    >
                      Next Step <ArrowRight className="h-4 w-4 ml-1.5" />
                    </Button>
                  </>
                ) : (
                  <Button
                    variant="default"
                    size="sm"
                    className="font-bold bg-primary hover:bg-primary/90 text-primary-foreground shadow-md"
                    loading={generating}
                    onClick={handleGenerate}
                  >
                    <Sparkles className="h-4 w-4 mr-1.5" />
                    Generate Grounded Knowledge with AI
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* AI GENERATION PREVIEW & APPROVE CARD                                */}
      {/* ------------------------------------------------------------------- */}
      {generatedDoc && (
        <Card className="border-primary/40 bg-primary/5 shadow-md">
          <CardHeader className="pb-3 border-b border-primary/20">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <CardTitle className="text-base font-bold flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-primary" />
                  Generated Grounded Knowledge Preview: &quot;{generatedDoc.title}&quot;
                </CardTitle>
                <CardDescription className="text-xs">
                  Review and edit the structured text. Only approved knowledge is indexed and retrievable during calls.
                </CardDescription>
              </div>
              <Badge variant="success" className="font-bold">
                Health Score: {generatedDoc.health_score}%
              </Badge>
            </div>
          </CardHeader>

          <CardContent className="pt-4 space-y-4">
            {/* Scoping Selector */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-surface rounded-xl border border-border">
              <div className="space-y-0.5">
                <span className="text-xs font-bold text-foreground">Scoping Assignment:</span>
                <p className="text-[11px] text-muted-foreground">
                  Choose whether this document is available to all agents or scoped strictly to {selectedAgent?.name || "the selected agent"}.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant={assignScope === "workspace" ? "default" : "secondary"}
                  className="text-xs h-7"
                  onClick={() => setAssignScope("workspace")}
                >
                  🌐 All Workspace Agents
                </Button>
                <Button
                  size="sm"
                  variant={assignScope === "agent" ? "default" : "secondary"}
                  className="text-xs h-7"
                  disabled={selectedAgentId === "all"}
                  onClick={() => setAssignScope("agent")}
                >
                  🤖 Scoped to {selectedAgent?.name || "Selected Agent"}
                </Button>
              </div>
            </div>

            {/* Editable Content Area */}
            <div>
              <Label className="text-xs font-semibold mb-1 block">Editable Knowledge Text:</Label>
              <Textarea
                rows={12}
                value={generatedDoc.text}
                onChange={(e) => setGeneratedDoc({ ...generatedDoc, text: e.target.value })}
                className="font-mono text-xs leading-relaxed bg-surface"
              />
            </div>

            {/* Action Bar */}
            <div className="flex items-center justify-between pt-2">
              <Button
                variant="ghost"
                size="sm"
                className="text-xs"
                onClick={handleGenerate}
                loading={generating}
              >
                <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Regenerate
              </Button>

              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  className="text-xs"
                  onClick={() => setGeneratedDoc(null)}
                >
                  Cancel
                </Button>
                <Button
                  variant="default"
                  size="sm"
                  className="text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm"
                  loading={approving}
                  onClick={handleApproveAndIndex}
                >
                  <Check className="h-4 w-4 mr-1.5" /> Approve &amp; Index for Live Calls
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* TAB 2 & 3: Write Text or Upload File                                */}
      {/* ------------------------------------------------------------------- */}
      {(activeTab === "text" || activeTab === "upload") && (
        <Card>
          <CardHeader>
            <CardTitle>{activeTab === "text" ? "Write or Paste Content" : "Upload File or Import Website"}</CardTitle>
            <CardDescription>
              Add plain text, PDF, DOCX, CSV, or import public FAQs from your website.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <QuickAddForm
              workspaceId={workspaceId}
              mode={activeTab}
              selectedAgentId={selectedAgentId}
              onDocumentCreated={(newDoc) => setDocuments((prev) => [newDoc, ...prev])}
            />
          </CardContent>
        </Card>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 4. In-Page "Ask Your Agent" Tester                                  */}
      {/* ------------------------------------------------------------------- */}
      <Card className="border-border">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <Bot className="h-4 w-4 text-primary" />
                Ask Your Agent (In-Page Knowledge Test)
              </CardTitle>
              <CardDescription className="text-xs">
                Test how the agent will respond on live calls using only approved scoped knowledge.
              </CardDescription>
            </div>
            <Badge variant="outline" className="text-[10px]">
              {selectedAgentId === "all" ? "Workspace-Wide Retrieval" : `Scoped: ${selectedAgent?.name}`}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Input
              value={testQuery}
              onChange={(e) => setTestQuery(e.target.value)}
              placeholder="e.g. Do you open on Sundays? or What is your return policy?"
              onKeyDown={(e) => e.key === "Enter" && handleTestAgent()}
              className="text-xs"
            />
            <Button onClick={handleTestAgent} loading={testLoading} size="sm" className="font-bold">
              <Search className="h-4 w-4 mr-1" /> Ask Agent
            </Button>
          </div>

          {testResponse && (
            <div className="rounded-xl border border-border bg-surface p-4 text-xs space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Badge variant={testResponse.grounded ? "success" : "warning"}>
                    {testResponse.grounded ? "🟢 Grounded in Approved Knowledge" : "🟡 Ungrounded / Safe Fallback"}
                  </Badge>
                  <span className="text-muted-foreground text-[11px]">
                    Scope used: <strong>{testResponse.used_scope}</strong>
                  </span>
                </div>
                <span className="text-[11px] text-muted-foreground">
                  Latency: {testResponse.latency_ms?.total_ms ?? 0} ms
                </span>
              </div>

              <div className="p-3 bg-surface-raised rounded-lg border border-border">
                <p className="text-[11px] text-muted-foreground font-semibold mb-1">Agent Phone Response:</p>
                <p className="text-foreground text-sm font-medium leading-relaxed">&ldquo;{testResponse.answer}&rdquo;</p>
              </div>

              {testResponse.matched_chunks && testResponse.matched_chunks.length > 0 && (
                <div className="space-y-1.5 pt-1">
                  <p className="text-[11px] font-semibold text-muted-foreground">Cited Approved Chunks:</p>
                  <div className="space-y-1">
                    {testResponse.matched_chunks.map((chk, i) => (
                      <div key={i} className="p-2 rounded bg-surface border border-border/70 text-[11px]">
                        <span className="font-semibold text-primary">[{chk.document_title}]</span>{" "}
                        <span className="text-muted-foreground">(Score: {chk.score.toFixed(2)})</span>: {chk.text}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ------------------------------------------------------------------- */}
      {/* 5. Document List with Agent Scoping Badges                          */}
      {/* ------------------------------------------------------------------- */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base font-bold">Approved Knowledge Documents</CardTitle>
              <CardDescription className="text-xs">
                Showing {filteredDocuments.length} document{filteredDocuments.length === 1 ? "" : "s"} for{" "}
                {selectedAgentId === "all" ? "all workspace agents" : selectedAgent?.name}.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {filteredDocuments.length === 0 ? (
            <div className="p-8 text-center text-xs text-muted-foreground border border-dashed border-border rounded-xl">
              No approved knowledge documents for this scope yet. Complete the guided questionnaire above to generate your first document.
            </div>
          ) : (
            <div className="divide-y divide-border">
              {filteredDocuments.map((doc) => (
                <DocumentCardRow
                  key={doc.id}
                  workspaceId={workspaceId}
                  document={doc}
                  agents={agents}
                  onUpdate={(updated) =>
                    setDocuments((prev) => prev.map((d) => (d.id === updated.id ? updated : d)))
                  }
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Document Row with Scoping Badge & Inline Scoping Edit
// ---------------------------------------------------------------------------

function DocumentCardRow({
  workspaceId,
  document,
  agents,
  onUpdate,
}: {
  workspaceId: string;
  document: DocumentOut;
  agents: AgentOut[];
  onUpdate: (doc: DocumentOut) => void;
}) {
  const { toast } = useToast();
  const [busy, setBusy] = React.useState(false);
  const [editingScope, setEditingScope] = React.useState(false);
  const [targetScope, setTargetScope] = React.useState<"workspace" | "agent">(
    document.scope === "agent" ? "agent" : "workspace"
  );
  const [selectedAgentIds, setSelectedAgentIds] = React.useState<string[]>(document.agent_ids || []);

  const handleReview = async (action: "approve" | "reject") => {
    setBusy(true);
    try {
      const res =
        action === "approve"
          ? await knowledgeApi.approveDocument(workspaceId, document.id, null)
          : await knowledgeApi.rejectDocument(workspaceId, document.id, null);
      onUpdate(res);
      toast({ title: `Document ${action}d`, variant: "success" });
    } catch (err) {
      toast({ title: "Action failed", variant: "danger" });
    } finally {
      setBusy(false);
    }
  };

  const handleSaveScope = async () => {
    setBusy(true);
    try {
      const res = await knowledgeApi.updateDocumentAgents(workspaceId, document.id, {
        scope: targetScope,
        agent_ids: targetScope === "agent" ? selectedAgentIds : [],
      });
      onUpdate(res);
      setEditingScope(false);
      toast({ title: "Scope updated successfully", variant: "success" });
    } catch (err) {
      toast({ title: "Failed to update scope", variant: "danger" });
    } finally {
      setBusy(false);
    }
  };

  const assignedAgentNames = (document.agent_ids || [])
    .map((aid) => agents.find((a) => a.id === aid)?.name)
    .filter(Boolean);

  return (
    <div className="py-3.5 space-y-2">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <FileText className="h-5 w-5 text-muted-foreground mt-0.5 shrink-0" />
          <div className="space-y-0.5">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-foreground">{document.title}</span>
              <Badge variant={APPROVAL_STATE_VARIANT[document.approval_state] ?? "secondary"} className="text-[10px]">
                {document.approval_state}
              </Badge>
              <Badge
                variant={document.scope === "agent" ? "default" : "outline"}
                className="text-[10px] cursor-pointer"
                onClick={() => setEditingScope(!editingScope)}
              >
                {document.scope === "agent"
                  ? `🤖 ${assignedAgentNames.length > 0 ? assignedAgentNames.join(", ") : "Agent Scoped"}`
                  : "🌐 Workspace-Wide"}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              {document.source_type} · {document.chunk_count} chunk{document.chunk_count === 1 ? "" : "s"} · Language:{" "}
              {document.language || "en-IN"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {document.approval_state === "needs_review" && (
            <>
              <Button size="sm" variant="secondary" onClick={() => handleReview("approve")} loading={busy} className="h-7 text-xs font-bold">
                Approve
              </Button>
              <Button size="sm" variant="ghost" onClick={() => handleReview("reject")} loading={busy} className="h-7 text-xs text-danger">
                Reject
              </Button>
            </>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="text-xs h-7 text-muted-foreground hover:text-foreground"
            onClick={() => setEditingScope(!editingScope)}
          >
            Edit Scope
          </Button>
        </div>
      </div>

      {/* Scope Editor Drawer / Form */}
      {editingScope && (
        <div className="p-3 bg-surface-raised rounded-xl border border-border space-y-3 text-xs">
          <p className="font-bold text-foreground">Configure Document Agent Scoping:</p>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="radio"
                name={`scope-${document.id}`}
                checked={targetScope === "workspace"}
                onChange={() => setTargetScope("workspace")}
              />
              <span>Workspace-Wide (Available to all agents)</span>
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="radio"
                name={`scope-${document.id}`}
                checked={targetScope === "agent"}
                onChange={() => setTargetScope("agent")}
              />
              <span>Scoped to specific agents only</span>
            </label>
          </div>

          {targetScope === "agent" && (
            <div className="space-y-1.5 pt-1">
              <p className="text-[11px] text-muted-foreground font-semibold">Select Assigned Agents:</p>
              <div className="flex flex-wrap gap-2">
                {agents.map((ag) => {
                  const isChecked = selectedAgentIds.includes(ag.id);
                  return (
                    <button
                      key={ag.id}
                      type="button"
                      onClick={() =>
                        setSelectedAgentIds((prev) =>
                          isChecked ? prev.filter((id) => id !== ag.id) : [...prev, ag.id]
                        )
                      }
                      className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors ${
                        isChecked
                          ? "bg-primary text-primary-foreground border-primary"
                          : "bg-surface text-foreground border-border hover:bg-surface-raised"
                      }`}
                    >
                      {ag.name} ({ag.persona_template ?? "Standard"})
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/60">
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setEditingScope(false)}>
              Cancel
            </Button>
            <Button size="sm" variant="default" className="h-7 text-xs font-bold" onClick={handleSaveScope} loading={busy}>
              Save Scope
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Quick Add Form for Text & Upload Tabs
// ---------------------------------------------------------------------------

function QuickAddForm({
  workspaceId,
  mode,
  selectedAgentId,
  onDocumentCreated,
}: {
  workspaceId: string;
  mode: "text" | "upload";
  selectedAgentId: string;
  onDocumentCreated: (doc: DocumentOut) => void;
}) {
  const router = useRouter();
  const { toast } = useToast();
  const [title, setTitle] = React.useState("");
  const [rawText, setRawText] = React.useState("");
  const [sourceUrl, setSourceUrl] = React.useState("");
  const [sourceType, setSourceType] = React.useState<string>(mode === "text" ? "text" : "pdf");
  const [file, setFile] = React.useState<File | null>(null);
  const [scope, setScope] = React.useState<"workspace" | "agent">(selectedAgentId !== "all" ? "agent" : "workspace");
  const [loading, setLoading] = React.useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      toast({ title: "Title is required", variant: "danger" });
      return;
    }
    setLoading(true);
    try {
      let fileBase64: string | undefined;
      if (mode === "upload" && sourceType !== "website") {
        if (!file) {
          toast({ title: "Please choose a file to upload", variant: "danger" });
          setLoading(false);
          return;
        }
        fileBase64 = await fileToBase64(file);
      }

      const doc = await knowledgeApi.createDocument(workspaceId, {
        source_type: (mode === "text" ? "text" : sourceType) as any,
        title,
        scope,
        agent_ids: scope === "agent" && selectedAgentId !== "all" ? [selectedAgentId] : [],
        raw_text: mode === "text" ? rawText : undefined,
        source_url: mode === "upload" && sourceType === "website" ? sourceUrl : undefined,
        file_base64: fileBase64,
      });

      await knowledgeApi.processDocument(workspaceId, doc.id);
      await knowledgeApi.approveDocument(workspaceId, doc.id, "Quick approved");

      toast({ title: "Document processed and approved!", variant: "success" });
      onDocumentCreated(doc);
      setTitle("");
      setRawText("");
      setSourceUrl("");
      setFile(null);
      router.refresh();
    } catch (err) {
      toast({
        title: "Upload failed",
        description: err instanceof ApiClientError ? err.message : "Error adding document",
        variant: "danger",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <Label htmlFor="qa-title">Document Title *</Label>
        <Input id="qa-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Return Policy FAQ" />
      </div>

      {mode === "upload" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <Label htmlFor="qa-type">Upload Source</Label>
            <select
              id="qa-type"
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value)}
              className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
            >
              <option value="pdf">PDF Document (.pdf)</option>
              <option value="docx">Word Document (.docx)</option>
              <option value="csv">CSV Spreadsheet (.csv)</option>
              <option value="website">Website URL (Scrape FAQs)</option>
            </select>
          </div>
          <div>
            {sourceType === "website" ? (
              <div>
                <Label htmlFor="qa-url">Website URL *</Label>
                <Input
                  id="qa-url"
                  value={sourceUrl}
                  onChange={(e) => setSourceUrl(e.target.value)}
                  placeholder="https://example.com/faqs"
                />
              </div>
            ) : (
              <div>
                <Label htmlFor="qa-file">Choose File *</Label>
                <input
                  id="qa-file"
                  type="file"
                  accept={sourceType === "pdf" ? ".pdf" : sourceType === "docx" ? ".docx" : ".csv"}
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="block w-full text-sm text-muted-foreground mt-1"
                />
              </div>
            )}
          </div>
        </div>
      )}

      {mode === "text" && (
        <div>
          <Label htmlFor="qa-text">Plain Text Content *</Label>
          <Textarea
            id="qa-text"
            rows={6}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder="Paste your FAQs, price list, or policy text here..."
          />
        </div>
      )}

      <div className="flex items-center justify-between pt-2">
        <div className="flex items-center gap-3 text-xs">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input type="radio" checked={scope === "workspace"} onChange={() => setScope("workspace")} />
            <span>Workspace-Wide</span>
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input type="radio" checked={scope === "agent"} onChange={() => setScope("agent")} />
            <span>Agent-Scoped</span>
          </label>
        </div>

        <Button type="submit" loading={loading} className="font-bold">
          Upload &amp; Approve
        </Button>
      </div>
    </form>
  );
}
