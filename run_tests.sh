#!/bin/bash

# Test runner script for Chatico Mapper App

set -e

echo "🧪 Running Chatico Mapper App Test Suite"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    print_error "Please run this script from the project root directory"
    exit 1
fi

# Check if poetry is installed
if ! command -v poetry &> /dev/null; then
    print_error "Poetry is not installed. Please install Poetry first."
    exit 1
fi

# Check if pytest is available
if ! poetry run pytest --version &> /dev/null; then
    print_warning "Installing test dependencies..."
    poetry install --with dev
fi

# Parse command line arguments
RUN_UNIT=true
RUN_INTEGRATION=true
RUN_COVERAGE=true
VERBOSE=false
PARALLEL=false
MARKERS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --unit-only)
            RUN_INTEGRATION=false
            RUN_COVERAGE=false
            shift
            ;;
        --integration-only)
            RUN_UNIT=false
            RUN_COVERAGE=false
            shift
            ;;
        --no-coverage)
            RUN_COVERAGE=false
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --parallel|-p)
            PARALLEL=true
            shift
            ;;
        --markers|-m)
            MARKERS="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --unit-only          Run only unit tests"
            echo "  --integration-only   Run only integration tests"
            echo "  --no-coverage        Skip coverage reporting"
            echo "  --verbose, -v        Verbose output"
            echo "  --parallel, -p       Run tests in parallel"
            echo "  --markers, -m        Run tests with specific markers"
            echo "  --help, -h           Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                           # Run all tests with coverage"
            echo "  $0 --unit-only              # Run only unit tests"
            echo "  $0 --integration-only       # Run only integration tests"
            echo "  $0 --markers 'slow'         # Run only slow tests"
            echo "  $0 --parallel --verbose     # Run tests in parallel with verbose output"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Build pytest command
PYTEST_CMD="poetry run pytest"

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

if [ "$PARALLEL" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -n auto"
fi

if [ "$RUN_COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=app --cov-report=term-missing --cov-report=html:htmlcov"
fi

if [ -n "$MARKERS" ]; then
    PYTEST_CMD="$PYTEST_CMD -m '$MARKERS'"
fi

# Add test paths based on what to run
if [ "$RUN_UNIT" = true ] && [ "$RUN_INTEGRATION" = true ]; then
    PYTEST_CMD="$PYTEST_CMD tests/"
elif [ "$RUN_UNIT" = true ]; then
    PYTEST_CMD="$PYTEST_CMD tests/unit/"
elif [ "$RUN_INTEGRATION" = true ]; then
    PYTEST_CMD="$PYTEST_CMD tests/integration/"
fi

print_status "Running tests with command: $PYTEST_CMD"
echo ""

# Run the tests
if eval $PYTEST_CMD; then
    print_success "All tests passed! 🎉"
    
    if [ "$RUN_COVERAGE" = true ]; then
        print_status "Coverage report generated in htmlcov/index.html"
    fi
    
    echo ""
    print_status "Test Summary:"
    if [ "$RUN_UNIT" = true ]; then
        echo "  ✅ Unit tests: PASSED"
    fi
    if [ "$RUN_INTEGRATION" = true ]; then
        echo "  ✅ Integration tests: PASSED"
    fi
    if [ "$RUN_COVERAGE" = true ]; then
        echo "  ✅ Coverage report: GENERATED"
    fi
    
    exit 0
else
    print_error "Some tests failed! ❌"
    echo ""
    print_status "Check the output above for details."
    print_status "You can also run specific test files or markers:"
    echo "  poetry run pytest tests/unit/test_instagram_service.py"
    echo "  poetry run pytest -m 'slow'"
    echo "  poetry run pytest -k 'test_webhook'"
    
    exit 1
fi
