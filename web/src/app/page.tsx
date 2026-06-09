import Navbar from '@/components/landing/Navbar'
import Hero from '@/components/landing/Hero'
import StatBand from '@/components/landing/StatBand'
import Problem from '@/components/landing/Problem'
import HowItWorks from '@/components/landing/HowItWorks'
import Features from '@/components/landing/Features'
import ProductShowcase from '@/components/landing/ProductShowcase'
import Personas from '@/components/landing/Personas'
import Pricing from '@/components/landing/Pricing'
import Testimonials from '@/components/landing/Testimonials'
import FAQ from '@/components/landing/FAQ'
import CTABand from '@/components/landing/CTABand'
import Footer from '@/components/landing/Footer'

export default function HomePage() {
  return (
    <main>
      <Navbar />
      <Hero />
      <StatBand />
      <Problem />
      <HowItWorks />
      <Features />
      <ProductShowcase />
      <Personas />
      <Pricing />
      <Testimonials />
      <FAQ />
      <CTABand />
      <Footer />
    </main>
  )
}
