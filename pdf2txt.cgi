#!/usr/bin/perl

# pdf2txt.cgi - given an OCR'd PDF file, return the underlying text, generate a report, and provide a concordance

# Eric Lease Morgan <emorgan@nd.edu>
# October   29, 2013 - started using Tika
# October   10, 2013 - added unigrams, bigrams, and concordance
# September 29, 2013 - added verb lemmas
# September 18, 2013 - added charts for readability as well as map; getting messy 
# September 16, 2013 - first investigations;


# configure
use constant TIKA      => "java -jar /var/www/html/sandbox/pdf2txt/etc/tika-app-1.4.jar -t ";
use constant TEMPDIR   => '/var/www/html/sandbox/pdf2txt/tmp/';
use constant ROOT      => 'http://dh.crc.nd.edu/sandbox/pdf2txt/tmp/';
use constant MAX       => 50;
use constant RADIUS    => 40;
use constant MAXVERBS  => 25;



# require
use CGI;
use CGI::Carp qw( fatalsToBrowser );
use Lingua::Concordance;
use Lingua::EN::Fathom;
use Lingua::EN::Ngram;
use Lingua::EN::Tagger;
use Lingua::StopWords qw( getStopWords );
use Lingua::TreeTagger;
use Math::Round;
use strict;
use HTML::TagCloud::Centred;

# initialize
my $cgi = CGI->new;
my $cmd = $cgi->param( 'cmd' );

# branch according to the hidden command; no command
if ( ! $cmd ) {

	print $cgi->header( 'Content-Type' => 'text/html' );
	print &form;
	
}

# list sentences with selected verb lemmas
elsif ( $cmd eq 'verbs' ) {

	my $lemma = $cgi->param( 'lemma' );
	my $id    = $cgi->param( 'id' );
	
	# build filename from id
	my $file = TEMPDIR . $id . '.txt';
	
	# tag the text
	my $tagger = Lingua::TreeTagger->new( 'language' => 'english' );
	my $tagged_text = $tagger->tag_file( $file );

	# find the original words associated with the choosen lemma
	my %originals = ();
	foreach my $token ( @{ $tagged_text->sequence() } ) {

		next if ( $token->lemma ne $lemma );
		$originals{ $token->original }++

	}

	# build a regular expression to use a query
	my $pattern = '';
	foreach my $original ( keys %originals ) { $pattern .= "\\b$original\\b|" }
	chop $pattern;

	# extract all the sentences
	my $tagger = new Lingua::EN::Tagger;
	my $tagged_text = $tagger->add_tags( &slurp( $file ) );
	my $sentences = $tagger->get_sentences( $tagged_text );

	# find sentences containing the originals, and mark them up
	my $output = '';
	foreach ( @$sentences ) { if ( $_ =~ /$pattern/ ) { $output .= '<li>' . &escape_entities( $_ ) . '</li>' } }
	$output =~ s|($pattern)|<b style='color:red'>$1</b>|gi;

	# done
	print $cgi->header( 'Content-Type' => 'text/html' );
	print &sentences( $cgi->ol( $output ) );
	
}

# generate simple report
elsif ( $cmd eq 'report' ) {

	# generate an identifier
	my $id = time;
	
	# convert the PDF to text and clean up
	my $file = $cgi->tmpFileName( $cgi->param( 'file' ));
	my $tmp = TEMPDIR . "$id";
	link $file, $tmp;

	# do the work
	my $cmd  = TIKA . $tmp;
	my $text = `$cmd`;
	#unlink $tmp;

	# save the Results
	open TMP, ' > ' . TEMPDIR . "$id.txt";
	print TMP $text;
	close TMP;
	
	# generate a URL for the result
	my $url = ROOT . "$id.txt";
	
	# initialize simple processing against the text
	my $collocations = Lingua::EN::Ngram->new( text => $text );
	my $stopwords    = &getStopWords( 'en' );
		
	# capture unigrams
	my $words    = $collocations->ngram( 1 );
	my $unigrams = HTML::TagCloud::Centred->new( size_max_pc => 150, clr_max => "#F705FF", clr_min => "#BB04C1" );
	my $index    = 0;
	foreach ( sort { $$words{ $b } <=> $$words{ $a } } keys %$words ) {
	
		# skip stopwords and punctuation
		next if ( $$stopwords{ $_ } );
		next if ( $_ =~ /[,.?!:;()\-]/ or $_ =~ /^'/ or $_ =~ /'$/ or length $_ == 1 );
		
		# limit the output
		$index++;
		last if ( $index > MAX );
		
		# gather the words
		#my $link = $cgi->a({ href => "./pdf2txt.cgi?cmd=search&id=$id&query=" . $_ }, $_ );
		#$unigrams .= $link . ' (' . $$words{ $_ } . '); &nbsp;';
		
		$unigrams->add( $_, "./pdf2txt.cgi?cmd=search&id=$id&query=" . $_, $$words{ $_ } );
	
	}
	$unigrams = $unigrams->html_and_css( 50 );

	# capture bigrams
	my $index   = 0;
	my $bigrams = $collocations->ngram( 2 );
	my $count   = $collocations->tscore;
	my $phrases = HTML::TagCloud::Centred->new( html_esc_code => sub { return shift; }, size_max_pc => 150, clr_max => "#1019FF", clr_min => "#0D0EC8" );
	foreach my $phrase ( sort { $$count{ $b } <=> $$count{ $a } } keys %$count ) {
	
		# get the tokens of the phrase
		my @tokens = split / /, $phrase;
	
		# process each token; filter based on it's value
		my $found = 0;
		foreach ( @tokens ) {
				
			# skip punctuation, stopwords, and single-word tokens
			if ( $_ =~ /[,.?!:;()\-]/ or $_ =~ /^'/ or $_ =~ /'$/ or length $_ == 1 or $$stopwords{ $_ } ) {
			
				$found = 1;
				last;
				
			}
								
		}
		
		# loop if found an unwanted token
		next if ( $found );

		# limit the output
		$index++;
		last if ( $index > MAX );
		last if ( $$count{ $phrase } == 1 );
		
		# gather the phrases
		#my $link = $cgi->a({ href => "./pdf2txt.cgi?cmd=search&id=$id&query=" . $phrase }, $phrase );
		#$phrases .= $link . ' (' . $$bigrams{ $phrase } . '); &nbsp;';

		$phrases->add( $phrase, "./pdf2txt.cgi?cmd=search&id=$id&query=" . $phrase, $$bigrams{ $phrase } );

	}
	$phrases = $phrases->html_and_css( 50 );
	
	# capture readability
	my $readability = new Lingua::EN::Fathom;
	$readability->analyse_file( TEMPDIR . "$id.txt" );
	
	# display nouns and noun phrases
	
	# display verbs (lemmas)
	my $tagger = Lingua::TreeTagger->new( 'language' => 'english' );
	my $tagged_text = $tagger->tag_file( TEMPDIR . "$id.txt" );
	my %lemmas = ();
	foreach my $token ( @{ $tagged_text->sequence() } ) {

		next if ( $token->tag !~ /^V/ );
		$lemmas{ $token->lemma }++;
	
	}

	my $index = 0;
	my $verbs = HTML::TagCloud::Centred->new( size_max_pc => 150, clr_max => '#FF0000', clr_min => '#550000' );
	foreach my $verb ( sort { $lemmas{ $b } <=> $lemmas{ $a } } keys %lemmas ) {

		#my $link = $cgi->a({ href => "./pdf2txt.cgi?cmd=verbs&id=$id&lemma=$verb" }, $verb );
		#my $value = $lemmas{ $verb };
		#$verbs .= "$link ($value); ";

		$verbs->add( $verb, "./pdf2txt.cgi?cmd=verbs&id=$id&lemma=$verb", $lemmas{ $verb } );
	
		$index++;
		last if ( $index > MAXVERBS );
	
	}
	$verbs = $verbs->html_and_css( 50 );

	# display our results
	print $cgi->header( 'Content-Type' => 'text/html' );
	print &report( $url, $unigrams, $phrases, &round( $readability->flesch ), &round( $readability->kincaid ), $verbs );
	
}

elsif ( $cmd eq 'search' ) {

	# get the query
	my $query = $cgi->param( 'query' );
	my $id    = $cgi->param( 'id' );
	
	# build & configure concordance
	my $file = TEMPDIR . $id . '.txt';
	my $concordance = Lingua::Concordance->new;
	$concordance->text( &slurp( $file ));
	$concordance->radius( RADIUS );
	$concordance->query( $query );

	# do the work
	my $lines = '';
	my $index = 0;
	foreach my $line ( $concordance->lines ) {
	
		# build padding
		$index++;
		
		my $spaces = '';
		if ( length( $index ) == 1 ) { $spaces = '   ' }
		if ( length( $index ) == 2 ) { $spaces = '  ' }
		if ( length( $index ) == 3 ) { $spaces = ' ' }
		
		# format line
		$lines .= "$index.$spaces$line" . $cgi->br;
	
	}
	
	# calculate and configure map
	$concordance->scale( 10 );
	my $map = $concordance->map;
	my @keys = sort { $$map{ $b } <=> $$map{ $a }} keys %$map;
	my $greatest_value = $$map{ $keys[ 0 ]};
	@keys = sort { $a <=> $b } keys %$map;
	my $values = '';
	foreach ( @keys ) { $values .= $$map{ $_ } . ',' }
	$values = substr( $values, 0, -1 );
	my $showmap = qq[<a href="javascript:show_map('Number of times &quot;$query&quot; occurs in the text and where')">Show map</a>];

	# format results, some more
	my $pattern = '\w+' . $query . '\w+|' . $query . '\w+|' . $query . '|\w+' . $query ;
	$lines =~ s|($pattern)|<b style='color:red'>$1</b>|gi;
	
	# display our results
	print $cgi->header( 'Content-Type' => 'text/html' );
	print &concordance( $id, $query, $lines = $cgi->pre({ style => 'text-align: center' }, $lines ), $showmap, $greatest_value, $values );

}
 
# error; bogus message
else { print "Unknown value for cmd: $cmd. Call Eric." }

# done
exit;


sub concordance {

	my $id       = shift;
	my $query    = shift;
	my $lines    = shift;
	my $map      = shift;
	my $greatest = shift;
	my $values   = shift;
	
	return <<EOF
<html>
<head>
<title>PDF to text</title>
	<link rel="stylesheet" type="text/css" href="./etc/css/jquery-ui.css" />
	<script type="text/javascript" src="./etc/js/jquery-core.js"></script>
	<script type="text/javascript" src="./etc/js/jquery-addons.js"></script>
	<script type="text/javascript">
		
		// show the size dialog
		function show_map(t) {
			\$("#map").dialog(
				{
					disabled: false,
					height: 350,
					modal: true,
					resizable: false,
					title: t,
					width: 475
				}
			);
		};
		
		// show the diagram dialog
		function show_diagram(t) {
			\$("#diagram").dialog(
				{
					disabled: false,
					height: 350,
					modal: true,
					resizable: false,
					title: t,
					width: 475
				}
			);
		};
	</script>
</head>
<body style='margin: 7%; text-align: center'>
<h1>PDF to text -- Concordance</h1>
<!-- map dialog box -->
<div id="map" style='text-align: center; display: none'>
	<img src="http://chart.apis.google.com/chart?chxr=0,10,100|1,0,$greatest&chxt=x,y&chbh=a&chs=425x205&cht=bvs&chds=0,$greatest&chd=t:$values" width="425" height="205" alt="map" />
</div>
<!-- network diagram -->
<div id="diagram" style='text-align: center; display: none'>
	<script type="text/javascript+protovis">
	
		var w = 550,
			h = 550;
		
		var vis = new pv.Panel()
			.width(w)
			.height(h)
			.fillStyle("white")
			.event("mousedown", pv.Behavior.pan())
			.event("mousewheel", pv.Behavior.zoom());
		
		var force = vis.add(pv.Layout.Force)
			.nodes(corpus.nodes)
			.links(corpus.links)
			.springLength(50)
			.chargeConstant(-1750)
			.bound(true);
			
		force.link.add(pv.Line);
		
		force.node.add(pv.Dot)
			.size(function(d) (d.linkDegree + 175) * Math.pow(this.scale, -1.5))
			.lineWidth(.5)
			.fillStyle("pink")
			.title(function(d) d.nodeName)
			.event("mousedown", pv.Behavior.drag())
			.event("drag", force);
		
		force.label.add(pv.Label).font('14px sans-serif');
		
		vis.render();
	
	</script>
</div>
<form method='GET' action='./pdf2txt.cgi'>
<input type='hidden' name='id' value='$id'>
<input type='hidden' name='cmd' value='search'>
<input type='text' name='query' value='$query'>
<input type="submit" value="Search">
</form>
<p>$map &nbsp;<a href="javascript:show_diagram('Network diagram')">Show diagram</a></p>
$lines
<hr />
<p style='font-size: small; color: silver'>Eric Lease Morgan &lt;<a href="mailto:emorgan\@nd.edu">emorgan\@nd.edu</a>&gt; -- <a href="http://dh.crc.nd.edu/sandbox/pdf2txt/pdf2txt.cgi">http://dh.crc.nd.edu/sandbox/pdf2txt/pdf2txt.cgi</a> -- October 10, 2013</p>
</body>
</html>
EOF

}


sub report {

	# get input
	my $url     = shift;
	my $words   = shift;
	my $phrases = shift;
	my $flesch  = shift;
	my $kincaid = shift;
	my $verbs   = shift;
	
	# re-configure kincaid
	my $percent = &round(( $kincaid * 100 ) / 20);
	
	return <<EOF
<html>
<head>
<title>PDF to text</title>
	<link rel="stylesheet" type="text/css" href="./etc/css/jquery-ui.css" />
	<script type="text/javascript" src="./etc/js/jquery-core.js"></script>
	<script type="text/javascript" src="./etc/js/jquery-addons.js"></script>
	<script type="text/javascript">
				
		// show the grade dialog
		function show_grade(t) {
			\$("#grade").dialog(
				{
					disabled: false,
					height: 275,
					modal: true,
					resizable: false,
					title: t,
					width: 475
				}
			);
		};
		
		// show the Flesch dialog
		function show_flesch(t) {
			\$("#flesch").dialog(
				{
					disabled: false,
					height: 275,
					modal: true,
					resizable: false,
					title: t,
					width: 475
				}
			);
		};
		
	</script>
</head>
<body style='margin: 7%; text-align: center'>
<h1>PDF to text -- Results</h1>

<!-- flesch dialog box -->
<div id="flesch" style='text-align: center; display: none'>
	<img src="http://chart.apis.google.com/chart?chxl=0:|very%20difficult|average|very%20easy&chxp=0,50,100&chxt=y&chs=425x205&cht=gm&chd=t0:$flesch" width="425" height="205" alt="Flesch" />
</div>

<!-- grade dialog box -->
<div id="grade" style='text-align: center; display: none'>
	<img src="http://chart.apis.google.com/chart?chxl=0:|grade|high|college|grad&chxp=0,6.5,10.5,14.7,17&chxr=0,0,17&chxt=y&chs=425x205&cht=gm&chd=t0:$percent" width="425" height="205" alt="grade" />
</div>

<p>
<strong>Extracted text</strong><br />
<a href="$url">$url</a>
</p>

<p><strong>Readability scores</strong><br />
<a href="javascript:show_flesch('Flesch score: $flesch')">$flesch</a> (Flesch),
<a href="javascript:show_grade('Kincaid level: $kincaid')">$kincaid</a> (Kincaid grade level)
</p>

<p>
<br /><strong>Most frequent unigrams</strong><br />
$words
</p>

<p>
<br /><strong>Most frequent bigrams</strong><br />
$phrases
</p>

<p>
<br /><strong>Most frequent verbs</strong><br />
$verbs
</p>

<hr />
<p style='font-size: small; color: silver'>Eric Lease Morgan &lt;<a href="mailto:emorgan\@nd.edu">emorgan\@nd.edu</a>&gt; -- <a href="http://dh.crc.nd.edu/sandbox/pdf2txt/pdf2txt.cgi">http://dh.crc.nd.edu/sandbox/pdf2txt/pdf2txt.cgi</a> -- October 10, 2013</p>
</body>
</html>
EOF

}


sub form {

	return <<EOF
<html>
<head>
<title>PDF to text</title>
</head>
<body style='margin: 7%; text-align: center'>
<h1>PDF to text</h1>
<p style='font-size: x-large'>Select a file from your computer, and I'll try to extract its underlying plain text.</p>
<form method='POST' action='./pdf2txt.cgi' enctype="multipart/form-data" >
<input type="hidden" name="cmd" value='report'>
<input type="file" name="file">
<input type="submit" value="Do it!">
</form>
<hr />
<p style='font-size: small; color: silver'>Eric Lease Morgan &lt;<a href="mailto:emorgan\@nd.edu">emorgan\@nd.edu</a>&gt; -- <a href="http://dh.crc.nd.edu/sandbox/pdf2txt/pdf2txt.cgi">http://dh.crc.nd.edu/sandbox/pdf2txt/pdf2txt.cgi</a> -- October 30, 2013</p>
</body>
</html>
EOF

}


sub sentences {

	my $sentences = shift;
	
	return <<EOF
<html>
<head>
<title>PDF to text</title>
<style>
	li { margin-bottom:1em; }
</style>
</head>
<body style='margin: 7%'>
$sentences
<hr />
<p style='font-size: small; color: silver'>Eric Lease Morgan &lt;<a href="mailto:emorgan\@nd.edu">emorgan\@nd.edu</a>&gt; -- <a href="http://dh.crc.nd.edu/sandbox/pdf2txt/pdf2txt.cgi">http://dh.crc.nd.edu/sandbox/pdf2txt/pdf2txt.cgi</a> -- October 10, 2013</p>
</body>
</html>
EOF

}

sub slurp {

	my $f = shift;
	open ( F, $f ) or die "Can't open $f: $!\n";
	my $r = do { local $/; <F> };
	close F;
	return $r;

}

sub escape_entities {

	# get the input
	my $s = shift;
	
	# escape
	$s =~ s/&/&amp;/g;
	$s =~ s/</&lt;/g;
	$s =~ s/>/&gt;/g;
	$s =~ s/"/&quot;/g;
	$s =~ s/'/&apos;/g;

	# done
	return $s;
	
}

