"""Generate self-signed SSL certificate for HTTPS"""
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import ipaddress
import os

def generate_self_signed_cert():
    """Generate self-signed SSL certificate"""
    
    print("=" * 60)
    print("Generating SSL self-signed certificate")
    print("=" * 60)
    
    # Generate private key
    print("\n1. Generating RSA private key...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # Create certificate subject
    print("2. Creating certificate...")
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"CN"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"Beijing"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"Beijing"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"PrecomControl"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"10.78.80.29"),
    ])
    
    # Create certificate
    now = datetime.now(timezone.utc)
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        now
    ).not_valid_after(
        now + timedelta(days=365)  # Valid for 1 year
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName(u"localhost"),
            x509.DNSName(u"127.0.0.1"),
            x509.IPAddress(ipaddress.IPv4Address(u"10.78.80.29")),
            x509.IPAddress(ipaddress.IPv4Address(u"127.0.0.1")),
        ]),
        critical=False,
    ).sign(private_key, hashes.SHA256(), default_backend())
    
    # Write certificate files
    cert_file = "cert.pem"
    key_file = "key.pem"
    
    print(f"3. Writing certificate files...")
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    with open(key_file, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    print("\n" + "=" * 60)
    print("SSL Certificate Generated Successfully!")
    print("=" * 60)
    print(f"Certificate file: {os.path.abspath(cert_file)}")
    print(f"Private key file: {os.path.abspath(key_file)}")
    print(f"Valid for: 1 year")
    print("\nNote: Self-signed certificate will show browser warning.")
    print("      Click 'Continue' or 'Accept Risk' to proceed.")
    print("=" * 60)

if __name__ == '__main__':
    generate_self_signed_cert()

