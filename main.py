import os
import jinja2
import webapp2
import json
import StringIO
import csv
import atom.data
import gdata.sample_util
import gdata.sites.client
import gdata.sites.data
import gdata.acl.data
import gdata.gauth

from google.appengine.api import rdbms
from google.appengine.api import users
from apiclient.discovery import build
from oauth2client.appengine import OAuth2Decorator
from datetime import datetime
from pytz import timezone
import pytz
from google.appengine.ext import blobstore
from google.appengine.ext import webapp
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.runtime import DeadlineExceededError
from gaesessions import get_current_session
from gaesessions import SessionMiddleware
from google.appengine.api import urlfetch
urlfetch.set_default_fetch_deadline(60)

JINJA_ENVIRONMENT = jinja2.Environment(
	loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    	extensions=['jinja2.ext.autoescape'])

_INSTANCE_NAME="prinya-th-2013:prinya-db"
SOURCE_APP_NAME = "my-prinya"
_CLIENT_ID = "380068443772.apps.googleusercontent.com"
_CLIENT_SECRET = "CnXNI8-u2QgJXpUs1BrBnmPP"

decorator = OAuth2Decorator(
	client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
	scope='https://www.googleapis.com/auth/plus.me https://www.googleapis.com/auth/plus.circles.read https://www.googleapis.com/auth/plus.circles.write')

service_plus = build('plus', 'v1domains')

class Core():
	IS_LOGIN = 0
	UNIVERSITY_ID = -1
	DOMAIN = ""
	EMAIL = ""
	STAFF_ID = ""
	FIRSTNAME = ""
	LASTNAME = ""
	IS_SHOW_POPUP = 0
	POPUP_MSG = ""
	
	@decorator.oauth_required
	def __init__(self):
		self.response.write("Create CoreData")

	# This function is to initialize important variables
        # such as FIRSTNAME, LASTNAME, and
        # UNIVERSITY_ID of the user logs on
	@staticmethod
	def login(self):
		user = users.get_current_user()
        	if not user:
			Core.IS_LOGIN = 0
			Core.UNIVERSITY_ID = -1
			Core.DOMAIN = ""
			Core.EMAIL = ""
			Core.STAFF_ID = ""
			Core.FIRSTNAME = ""
			Core.LASTNAME = ""
            		self.redirect(users.create_login_url(self.request.uri))
		else:
			session = get_current_session()
			if session.has_key('is_login'):
				return
			email = user.email()
			session['email'] = email
			conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
    			cursor = conn.cursor()

			domain = email[email.find('@'):len(email)]
			session['domain'] = domain
			cursor.execute("SELECT university_id, super FROM university WHERE domain='%s' LIMIT 1"%(domain))
			row = cursor.fetchall()
			if len(row)==0:
				self.redirect('/InvalidLogin')
			else:
				session['university_id'] = row[0][0]
				session['super'] = row[0][1]

			cursor.execute("SELECT staff_id, firstname, lastname FROM staff WHERE email='%s' AND university_id='%s' LIMIT 1"%(email, session['university_id']))
			row = cursor.fetchall()
			if len(row)==0:
				self.redirect('/InvalidLogin')
			else:
				Core.STAFF_ID = row[0][0]
				Core.FIRSTNAME = row[0][1]
				Core.LASTNAME = row[0][2]
				Core.IS_LOGIN = 1
				session['staff_id'] = row[0][0]
				session['firstname'] = row[0][1]
				session['lastname'] = row[0][2]
				session['is_login'] = 1
				self.redirect('/')

class Logout(webapp2.RequestHandler):
	# This function is exectued when the user requests with method POST
        # Terminate session before logging out	
	@decorator.oauth_required
	def post(self):
		Core.IS_LOGIN = 0
		Core.UNIVERSITY_ID = -1
		Core.DOMAIN = ""
		Core.EMAIL = ""
		Core.STAFF_ID = ""
		Core.FIRSTNAME = ""
		Core.LASTNAME = ""
		get_current_session().terminate()
		self.redirect(users.create_logout_url(self.request.uri))

	# This function is executed when the user requests with method GET
        # Terminate session before logging out		
	def get(self):
		Core.IS_LOGIN = 0
		Core.UNIVERSITY_ID = -1
		Core.DOMAIN = ""
		Core.EMAIL = ""
		Core.STAFF_ID = ""
		Core.FIRSTNAME = ""
		Core.LASTNAME = ""
		get_current_session().terminate()
		self.redirect(users.create_logout_url(self.request.uri))

class MainHandler(webapp2.RequestHandler):

	# This function is to retrieve course information from the 
        # database and display course information in the table	
	@decorator.oauth_required
	def get(self):

		Core.login(self)

		session = get_current_session()
		http = decorator.http()
		email = session['email']
		cal_src = "http://www.google.com/calendar/embed?src=" + email + "&ctz=Asia/Bangkok"
		templates = {
			'email' : email,
			'cal_src' : cal_src
		}
		template = JINJA_ENVIRONMENT.get_template('index.html')
		self.response.write(template.render(templates))

class Course(webapp2.RequestHandler):

	# This function is to retrieve course information from the 
        # database and display course information in the table	
	@decorator.oauth_required
	def get(self):

		Core.login(self)

		session = get_current_session()
		http = decorator.http()

		conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
		cursor = conn.cursor()
		cursor.execute("SELECT course_id,course_code,course_name,credit_lecture,credit_lab,credit_learning,status,regiscourse_id,department, faculty FROM course natural join regiscourse WHERE university_id=" + str(session['university_id']))

		course = cursor.fetchall()

		cursor.execute('SELECT sum(capacity),sum(enroll),regiscourse_id FROM section group by regiscourse_id')
        	enroll = cursor.fetchall()
		cursor.execute("SELECT * FROM faculty WHERE university_id=" + str(session['university_id']))
		faculty = cursor.fetchall()
		templates = {
			'email' : session['email'],
			'super' : session['super'],
			'course' : course,
			'enroll' : enroll,
			'faculty' : faculty,
		}

		template = JINJA_ENVIRONMENT.get_template('course.html')
		self.response.write(template.render(templates))

class search(webapp2.RequestHandler):
  	def post(self):

		Core.login(self)

  		course_code=self.request.get('keyword');
  		year=self.request.get('year');
  		
  		semester=self.request.get('semester');
  		check_code=0
  		check_fac=0
  		check_dep=0
  		check_year=0
  		check_sem=0
  		allcheck=0
  		key_year=""
  		key_sem=""
  		code=""

  		if year=="":
  			check_year=0
  		else:
  			check_year=1
  			key_year="year="+year

  		if semester=="":
  			check_sem=0
  		else:
  			check_sem=1
  			key_sem="semester="+semester

  		if course_code == "":
  			check_code=0

  		else:
  			check_code=1
  			code="course_code like '%"+course_code+"%' "

  		data_faculty_id=self.request.get('faculty');
  		data_faculty_id=str(data_faculty_id)
  		data_faculty=""
		for row in faculty:
			if data_faculty_id == row[0]:
				data_faculty =row[1];

		if data_faculty_id =="":
			check_fac=0
		else:
			check_fac=1
  		
  		
	
		data_department=self.request.get('department');
		data_department=str(data_department)
	

		if data_department=="":
			check_dep=0
		else:
			check_dep=1

		

		where_code=" "
		a=" and "

		

		if check_code == 1:
			if check_code == 1:
				where_code+=code
			if check_year == 1:
				where_code+=a
				where_code+=key_year
			if check_sem == 1:
				where_code+=a
				where_code+=key_sem
			if check_fac == 1:
				where_code+=a
				where_code+=data_faculty
			if check_dep==1:
				where_code+=a
				where_code+=data_department
		elif check_year == 1:
			if check_year == 1:
				where_code+=key_year
			if check_sem == 1:
				where_code+=a
				where_code+=key_sem
			if check_fac == 1:
				where_code+=a
				where_code+=data_faculty
			if check_dep==1:
				where_code+=a
				where_code+=data_department
		elif check_sem == 1:
			if check_sem == 1:
				where_code+=key_sem
			if check_fac == 1:
				where_code+=a
				where_code+=data_faculty
			if check_dep==1:
				where_code+=a
				where_code+=data_department
		elif check_fac == 1:
			if check_fac == 1:
				where_code+=data_faculty
			if check_dep==1:
				where_code+=a
				where_code+=data_department
		elif check_dep==1:
			if check_dep==1:
				where_code+=data_department
		else:
			where_code="course_id = 0"

		conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
    		cursor = conn.cursor()
    		sql="SELECT course_id,course_code,course_name,credit_lecture,credit_lab,credit_learning,status,regiscourse_id FROM course natural join regiscourse where %s "%(where_code)
                # sql="SELECT course_id,course_code,course_name,credit_lecture,credit_lab,credit_learning,status,regiscourse_id FROM course natural join regiscourse where course_code like '%s'"%(percent)
		cursor.execute(sql)
		conn.commit()
		

		conn2=rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
    		cursor2 = conn2.cursor()
		cursor2.execute('SELECT sum(capacity),sum(enroll),regiscourse_id FROM section group by regiscourse_id')
		conn2.commit()

		templates = {

			'course' : cursor.fetchall(),
			'enroll' : cursor2.fetchall(),

			}

		template = JINJA_ENVIRONMENT.get_template('course.html')
		self.response.write(template.render(templates))

		conn.close()
		conn2.close()

# Display form create course page
class CreateHandler(webapp2.RequestHandler):
    	@decorator.oauth_required
    	def get(self):

		Core.login(self)

		session = get_current_session()		

        	conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
        	cursor = conn.cursor()
        	cursor.execute("select * from course")
		course = cursor.fetchall()

		cursor.execute("SELECT * FROM faculty WHERE university_id=" + str(session['university_id']))
		faculty = cursor.fetchall()

		cursor.execute("select payment_type from university where university_id=%d"%(session['university_id']))
		pay_type = cursor.fetchall()[0][0]
        
        	templates = {
        		'email' : session['email'],
    			'course' : course,
			'pay_type' : pay_type,
			'faculty' : faculty,
    		}
    		get_template = JINJA_ENVIRONMENT.get_template('course_create.html')
    		self.response.write(get_template.render(templates));


class ErrorHandler(webapp2.RequestHandler):
    	@decorator.oauth_required
    	def get(self):
        	templates = {
            		# 'course' : cursor.fetchall(),
        	}
        	get_template = JINJA_ENVIRONMENT.get_template('error.html')
        	self.response.write(get_template.render(templates));
        	# self.redirect('/')

class ErrorDelHandler(webapp2.RequestHandler):
    	def get(self):
    		course_id = self.request.get('course_id');
        	templates = {
            		'course_id' : course_id,
        	}
        	get_template = JINJA_ENVIRONMENT.get_template('errordel.html')
        	self.response.write(get_template.render(templates));
        	# self.redirect('/')



# Display course detail page
class DetailCourseHandler(webapp2.RequestHandler):
    	@decorator.oauth_required
    	def get(self):

		Core.login(self)

		session = get_current_session()

        	course_id = self.request.get('course_code');
        	capacity=""

        	conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
        	cursor = conn.cursor()
            	sql="SELECT * FROM course WHERE course_code = '%s'"%(course_id)
        	cursor.execute(sql);

            	conn2 = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
            	cursor2 = conn2.cursor()
            	sql2="SELECT co.course_code FROM course co,prerequisite_course pre\
                	WHERE prerequisite_id=co.course_id AND pre.course_id=\
                	(SELECT course_id FROM course WHERE course_code='%s')"%(course_id)
            	cursor2.execute(sql2);
            	pre_code=""
            	for row in cursor2.fetchall():
                	pre_code=row[0]

    		conn3 = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
        	cursor3 = conn3.cursor()
            	sql3="SELECT sum(capacity) FROM section se JOIN regiscourse re\
            	ON se.regiscourse_id=re.regiscourse_id\
            	join course co\
            	ON co.course_id=re.course_id\
            	WHERE course_code='%s'"%(course_id)
        	cursor3.execute(sql3);
        	for capa in cursor3.fetchall():
        		if capa[0]!="":
        			capacity=capa[0]
        		else:
        			capacity=0

        		
        	conn3.close();
    	
            	templates = {
			'email' : session['email'],
			'domain' : session['domain'],
        		'course' : cursor.fetchall(),
        		'capacity' : capacity,
    			'prerequisite_code' : pre_code,
        	}
        	get_template = JINJA_ENVIRONMENT.get_template('course_detail.html')
        	self.response.write(get_template.render(templates));
            	conn.close();
            	conn2.close();

# Display modify course page
class ModifyCourseHandler(webapp2.RequestHandler):
    	@decorator.oauth_required
    	def get(self):

		Core.login(self)

		session = get_current_session()

        	course_id = self.request.get('course_id')
        	course_name = self.request.get('course_name')

        	conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
        	cursor = conn.cursor()
            	sql="SELECT * FROM course WHERE course_code = '%s'"%(course_id)
            	cursor.execute(sql);
		course = cursor.fetchall()

		cursor.execute("SELECT * FROM faculty WHERE university_id=" + str(session['university_id']))
		faculty = cursor.fetchall()

		cursor.execute('select department from course group by department')
		department = cursor.fetchall()

            	conn2 = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
            	cursor2 = conn2.cursor()
            	sql2="SELECT course_id,course_code from course where course_code not like '%s'"%(course_id)
            	cursor2.execute(sql2);

            	conn3 = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
            	cursor3 = conn3.cursor()
            	sql3="SELECT section_id,section_number,UPPER(CONCAT(CONCAT(firstname,' '),lastname)), circle_url, site_url,enroll,capacity\
                	FROM section sec JOIN staff st ON teacher_id=staff_id\
                	WHERE regiscourse_id=(SELECT regiscourse_id FROM regiscourse WHERE course_id=\
                	(SELECT course_id from course where course_code='%s')) ORDER BY section_number"%(course_id)
            	cursor3.execute(sql3);

            	conn4 = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
            	cursor4 = conn4.cursor()
            	sql4="SELECT co.course_id,co.course_code FROM course co,prerequisite_course pre\
                	WHERE prerequisite_id=co.course_id AND pre.course_id=\
                	(SELECT course_id FROM course WHERE course_code='%s')"%(course_id)
            	cursor4.execute(sql4);
            	pre_id=""
            	pre_code=""
            	for row in cursor4.fetchall():
                	pre_id=row[0]
                	pre_code=row[1]
		
		cursor.execute("select payment_type from university where university_id=%d"%(session['university_id']))
		pay_type = cursor.fetchall()[0][0]

            	templates = {
			'email' : session['email'],
			'domain' : session['domain'],
        		'course' : course,
                	'course2' : cursor2.fetchall(),
               		'course3' : cursor3.fetchall(),
                	'course_id' : course_id,
			'course_name' : course_name,
                	'prerequisite_id' : pre_id,
                	'prerequisite_code' : pre_code,
			'faculty' : faculty,
			'department' : department,
			'pay_type' : pay_type,
			'price' : course[0][9]
        	}
        	get_template = JINJA_ENVIRONMENT.get_template('course_modify.html')
        	self.response.write(get_template.render(templates));
            	conn.close();
            	conn2.close();
            	conn3.close();
            	conn4.close();

# Update course data from modify page
class UpdateCourseHandler(webapp2.RequestHandler):
    	@decorator.oauth_required
    	def post(self):

		Core.login(self)

		session = get_current_session()

        	course_id = self.request.get('course_id')
            	course_name = self.request.get('course_name')
            	prerequisite = self.request.get('prerequisite')
                if prerequisite!="":
                	prerequisite=int(prerequisite)
                course_description = self.request.get('course_description')
            	credit_lecture = self.request.get('credit_lecture')
                credit_lecture=int(credit_lecture)
                credit_lab = self.request.get('credit_lab')
                credit_lab=int(credit_lab)
                credit_learning = self.request.get('credit_learning')
                credit_learning=int(credit_learning)
            	faculty = self.request.get('faculty')
                department = self.request.get('department')
	 	price = self.request.get('price')

            	conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
            	cursor = conn.cursor()
        	sql="UPDATE course SET course_code = '%s' , \
                	course_name = '%s' , course_description = '%s' , \
                 	credit_lecture = '%d' , credit_lab = '%d' , \
                 	credit_learning = '%d' , department = '%s' , \
                 	faculty = '%s' ,price = '%s' \
                 	WHERE course_code = '%s'"%(course_id,course_name,course_description,credit_lecture,credit_lab,credit_learning,department,faculty,price,course_id)        
            	cursor.execute(sql);
                conn.commit();
                      
                sql="DELETE FROM prerequisite_course\
                        WHERE course_id=(SELECT course_id FROM course WHERE course_code = '%s')"%(course_id)
                cursor.execute(sql)        
                conn.commit()
                
                if prerequisite!="":
                    	sql="INSERT INTO prerequisite_course\
                                (course_id,type,prerequisite_id) VALUES((SELECT course_id FROM course WHERE course_code = '%s'),1,'%s')"%(course_id,prerequisite)
                    	cursor.execute(sql)        
                    	conn.commit()

                utc = pytz.utc
                date_object = datetime.today()
                utc_dt = utc.localize(date_object);
                bkk_tz = timezone("Asia/Bangkok");
                bkk_dt = bkk_tz.normalize(utc_dt.astimezone(bkk_tz))
                time_insert = bkk_dt.strftime("%H:%M:%S")

                sql="INSERT INTO log (staff_id,course_code,day,time,type, university_id)\
                    	VALUES((select staff_id from staff where type=2 AND email='%s' AND university_id='%s'),'%s',CURDATE(),'%s',4, '%d')"%(session['email'], session['university_id'],course_id,time_insert, session['university_id'])
                cursor.execute(sql)        
                conn.commit()
                conn.close();
                
                self.redirect("/ModifyCourse?course_id="+course_id+"&course_name="+course_name)

#//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

# Display add section form page
class AddSectionHandler(webapp2.RequestHandler):
    	@decorator.oauth_required
    	def get(self):

		Core.login(self)

		session = get_current_session()
        
    		course_id=self.request.get('course_id')
    		course_name = self.request.get('course_name')
            	conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
            	cursor = conn.cursor()
                sql="SELECT firstname FROM staff WHERE type=2 AND university_id=" + str(session['university_id'])
                cursor.execute(sql);
                templates = {
			'email' : session['email'],
                    	'course_id' : course_id,
                    	'course_name' : course_name,
                    	'name' : cursor.fetchall()
                }
                get_template = JINJA_ENVIRONMENT.get_template('section.html')
                self.response.write(get_template.render(templates));
                conn.commit();
                conn.close();        

# Create section from add section page
# Insert to database
# Create Google+ circle
# Create Mailing Group
class InsSectionHandler(webapp2.RequestHandler):
    	@decorator.oauth_required
    	def post(self):

		Core.login(self)

		session = get_current_session()
		http = decorator.http()

        	course_id=self.request.get('course_id')
		course_name=self.request.get('course_name')
                section_number=self.request.get('section_number')
                section_number=int(section_number)
                teacher=self.request.get('teacher')
                capacity=self.request.get('capacity')
                capacity=int(capacity)

		display_name = "prinya-course-" + course_id + "-" + str(section_number)
		params = {
			'displayName' : display_name
		}
		result = service_plus.circles().insert(userId="me",body=params).execute(http=http)
		circle_url = "https://plus.google.com/u/0/circles/" + display_name + "-p" + result['id']

                conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
                cursor = conn.cursor()
                sql="INSERT INTO section (regiscourse_id,section_number,teacher_id,capacity,enroll, circle_id, circle_url) \
                    	VALUES ((SELECT regiscourse_id FROM regiscourse WHERE course_id=(SELECT course_id FROM course where course_code = '%s')),'%d',\
                    	(SELECT staff_id FROM staff WHERE type=2 AND firstname='%s' AND university_id='%s'),'%d','0', '%s', '%s')"%(course_id,section_number,teacher,session['university_id'],capacity, str(result['id']), circle_url)
                cursor.execute(sql);
                conn.commit();
                conn.close();

		params = {
			'email': "prinya-course-" + course_id + "-" + str(section_number) + session['domain'],
			'name' : course_id + "-" + str(section_number)
		}
	
		result = service.groups().insert(body=params).execute(http=http)

                utc = pytz.utc
                date_object = datetime.today()
                utc_dt = utc.localize(date_object);
                bkk_tz = timezone("Asia/Bangkok");
                bkk_dt = bkk_tz.normalize(utc_dt.astimezone(bkk_tz))
                time_insert = bkk_dt.strftime("%H:%M:%S")

                conn2 = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
                cursor2 = conn2.cursor()
                sql2="INSERT INTO log (staff_id,course_code,day,time,type, university_id)\
                    	VALUES((select staff_id from staff where type=2 AND email='%s' AND university_id='%s'),'%s',CURDATE(),'%s',2, '%d')"%(session['email'], session['university_id'],course_id,time_insert, session['university_id'])
                cursor2.execute(sql2)        
                conn2.commit()
                conn2.close();

                #self.redirect("/ModifyCourse?course_id="+course_id)
		self.redirect("/CreateSecSites?course_id="+course_id+"&section_number="+str(section_number)+"&course_name="+course_name+"&teacher="+teacher)

class CreateSecSitesHandler(webapp2.RequestHandler):
	@decorator.oauth_required
	def get(self):
		
		Core.login(self)
		session = get_current_session()
		
		data_code = self.request.get('course_id')
		section_number = self.request.get('section_number')
		course_name = self.request.get('course_name')
		teacher = self.request.get('teacher')
		
		templates = {
			'email' : session['email'],
			'course_id' : data_code,
			'course_name' : course_name,
			'section_number' : section_number,
			'domain' : session['domain'].replace("@",""),
			'teacher' : teacher,
		}
		get_template = JINJA_ENVIRONMENT.get_template('sec_site_create.html')
		self.response.write(get_template.render(templates))

class InsertSecSitesHandler(webapp2.RequestHandler):
	@decorator.oauth_required
	def post(self):
		
		Core.login(self)
		session = get_current_session()
		
		site_sec_username = self.request.get('site_sec_username')
		site_sec_password = self.request.get('site_sec_password')
		data_code = self.request.get('course_id')
		section_number = self.request.get('section_number')
		course_name = self.request.get('course_name')
		teacher_name = self.request.get('teacher_name')

		try:
			teach_conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
			teach_cursor = teach_conn.cursor()
			teach_cursor.execute("SELECT email FROM staff WHERE firstname = '%s'"%(teacher_name))
			teach_fetch = teach_cursor.fetchall()
		
			teacher_email = teach_fetch[0]
		
			site_name = course_name+"-1-2556"
		
			client = gdata.sites.client.SitesClient(source=SOURCE_APP_NAME, site = site_name)
			client.ClientLogin(site_sec_username, site_sec_password, client.source)
			client.domain = session['domain'].replace("@","")
		
			site_sec_name = course_name + "-sec" + section_number + "-1-2556"
										   
			entry = client.CreateSite(site_sec_name, description='Testing of Prinya course site', theme='slate')
			site_sec_url = entry.GetAlternateLink().href
			"""
			scope = gdata.acl.data.AclScope(value=teacher_email, type='user')
			role = gdata.acl.data.AclRole(value='writer')
			acl = gdata.sites.data.AclEntry(scope=scope, role=role)
		
			acl_entry = client.Post(acl, client.MakeAclFeedUri())
			"""
			site_sec_conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
			site_sec_cursor = site_sec_conn.cursor()
			site_sec_cursor.execute("UPDATE section SET site_url = '%s' WHERE regiscourse_id = \
				(SELECT regiscourse_id FROM regiscourse WHERE course_id = \
				(SELECT course_id FROM course WHERE course_code = '%s')) AND section_number = '%d'"%(site_sec_url, data_code, int(section_number)))
			site_sec_conn.commit()
		
			self.redirect("/ModifyCourse?course_id="+data_code+"&course_name="+course_name)

		except DeadlineExceededError:
			self.response.clear()
            		self.response.headers['Location'] = response.geturl()
            		self.response.set_status(302)


#//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

# Display section detail page
class DetailSectionHandler(webapp2.RequestHandler):
    	@decorator.oauth_required
    	def get(self):

		Core.login(self)

		session = get_current_session()
        
                course_id=self.request.get('course_id')
                section_id=self.request.get('section_id')
                section_id=int(section_id)
                section_number=self.request.get('section_number')
                section_number=int(section_number)

                conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
                cursor = conn.cursor()

                sql="SELECT section_number,firstname,capacity\
                    	FROM section sec JOIN staff st ON teacher_id=staff_id\
                    	WHERE section_id='%d' AND section_number='%d'"%(section_id,section_number)
                cursor.execute(sql);

                conn2 = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
                cursor2 = conn2.cursor()
                sql2="SELECT sectime_id, CASE day WHEN '1' THEN 'Sunday'\
                    	WHEN '2' THEN 'Monday'\
                   	WHEN '3' THEN 'Tuesday'\
                    	WHEN '4' THEN 'Wednesday'\
                    	WHEN '5' THEN 'Thursday'\
                    	WHEN '6' THEN 'Friday'\
                    	WHEN '7' THEN 'Saturday'\
                    	ELSE 'ERROR' END,CONCAT(CONCAT(start_time,'-'),end_time),room FROM section_time WHERE section_id='%d'"%(section_id)
                cursor2.execute(sql2)

                templates = {
			'email' : session['email'],
                    	'section' : cursor.fetchall(),
                    	'time' : cursor2.fetchall(),
                    	'course_id' : course_id,
                    	'section_id' : section_id,
                    	'section_number' : section_number,
                }
                get_template = JINJA_ENVIRONMENT.get_template('secdetail.html')
                self.response.write(get_template.render(templates))
                conn.close()
                conn2.close()


# Display form create section time page
class AddSectimeHandler(webapp2.RequestHandler):
    	@decorator.oauth_required
    	def get(self):

		Core.login(self)

		session = get_current_session()
        
                course_id=self.request.get('course_id');
                section_id=self.request.get('section_id');
                section_id=int(section_id)
                section_number=self.request.get('section_number');
                section_number=int(section_number)

                templates = {
			'email' : session['email'],
                    	'course_id' : course_id,
                    	'section_id' : section_id,
                    	'section_number' : section_number,
                }
                get_template = JINJA_ENVIRONMENT.get_template('section_time.html')
                self.response.write(get_template.render(templates));


#//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
# Display invalid login message
class InvalidLogin(webapp2.RequestHandler):
	def get(self):
		self.response.write("Invalid Login")

# Query keyword and render html result
class AjaxSearch(webapp2.RequestHandler):
	def post(self):
		session = get_current_session()

		key = self.request.get('keyword')
		department = self.request.get('department')
		faculty = self.request.get('faculty')
		status = self.request.get('status').lower()
		if ("active".startswith(status) or status == "active"):
			status = "1"
		elif ("disable".startswith(status) or status == "disable"):
			status = "0"

		conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
    		cursor = conn.cursor()
        	sql = "SELECT course_id,course_code,course_name,credit_lecture,credit_lab,credit_learning,status,regiscourse_id, department, faculty FROM course c natural join regiscourse rc WHERE c.university_id='" + str(session['university_id']) + "' AND (c.course_code LIKE '%" + key + "%' OR c.course_name LIKE '%" + key + "%') AND c.department LIKE '%" + department + "%' AND c.faculty LIKE '%" + faculty + "%' AND rc.status='" + status + "'"
        	cursor.execute(sql)

		course = cursor.fetchall()
		templates = {
			'course' : course,
		}
		conn.close()

		template = JINJA_ENVIRONMENT.get_template('course_ajax.html')
		self.response.write(template.render(templates))


# Display manage credit page
class Credit(webapp2.RequestHandler):
	@decorator.oauth_required
	def get(self):

		Core.login(self)

		session = get_current_session()

		conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
    		cursor = conn.cursor()
		cursor.execute("SELECT * FROM faculty WHERE university_id=" + str(session['university_id']))
		faculty = cursor.fetchall()
		cursor.execute("SELECT payment_type FROM university WHERE university_id='%s'"%(str(session['university_id'])))
		payment_type = cursor.fetchall()
		templates = {
			'email' : session['email'],
			'super' : session['super'],
			'faculty' : faculty,
			'payment_type' : payment_type[0][0]
		}
		template = JINJA_ENVIRONMENT.get_template('credit.html')
		self.response.write(template.render(templates))

# Update credit data from manage credit page
class CreditHandler(webapp2.RequestHandler):
	def post(self):
		pay_type = self.request.get('rate')
		faculty = self.request.get('faculty')
		department = self.request.get('department')
		price = self.request.get('price')

		conn = rdbms.connect(instance=_INSTANCE_NAME, database='Prinya_Project')
    		cursor = conn.cursor()

		if pay_type == "spec":
			sql = "update university set payment_type=1"
			cursor.execute(sql)
			conn.commit();
		elif pay_type == "flat":
			sql = "update university set payment_type=2"
			cursor.execute(sql)
			conn.commit();

			sql = "update department set fee='%s' where department_name='%s' and faculty_id='%s'"%(price, department, faculty)
			self.response.write(sql)
			cursor.execute(sql)
			conn.commit()

		conn.close()
		self.redirect('/')


app = webapp2.WSGIApplication([
	('/', MainHandler),
	('/search',search),
	('/Error', ErrorHandler),
	('/DetailCourse',DetailCourseHandler),
	('/DetailSection',DetailSectionHandler),
	('/InvalidLogin',InvalidLogin),
	('/AjaxSearch',AjaxSearch),
	('/Credit', Credit),
	('/Course', Course),
	('/CreditHandler', CreditHandler),
	('/Logout', Logout),
	(decorator.callback_path, decorator.callback_handler())    
], debug=True)
app = SessionMiddleware(app, cookie_key=str(os.urandom(64)))
