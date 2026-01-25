export default {
  preset: 'ts-jest',
  testEnvironment: 'jsdom',
  transform: {
    '^.+\\.(ts|tsx)$': ['ts-jest', {
      tsconfig: 'tsconfig.test.json'
    }],
  },
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  testMatch: [
    '**/__tests__/**/*.(test|spec).tsx',
    '**/?(*.)+(test|spec).tsx'
  ],
  setupFilesAfterEnv: [
    '@testing-library/jest-dom'
  ],
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/main.tsx',
    '!src/App.tsx',
    '!src/vite-env.d.ts'
  ],
  coverageReporters: ['text', 'html'],
  coverageDirectory: 'coverage',
  modulePaths: ['<rootDir>/src'],
  extensionsToTreatAsEsm: ['.ts', '.tsx']
};